"""
Core routing for the five-category response contract (TRD TR12).

Translates a validated LLM metric selection into a MetricFlow query command,
runs it, and returns one of five categories:

* ``answered`` — valid execution (zero rows **is** ``answered`` per TR10)
* ``unknown_metric`` — metrics proposed that do not exist in the catalog (TR3)
* ``ambiguous`` — more than one metric proposed by the LLM
* ``unsupported_domain`` — domain not in the governed catalog
* ``system_error`` — MetricFlow or provider failure
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import catalog_builder

logger = logging.getLogger(__name__)

# The dbt project directory (where ``mf query`` expects to be run from).
DBT_DIR = os.environ.get("DBT_DIR", str(Path(__file__).resolve().parents[2] / "dbt"))

MF_QUERY_TIMEOUT = int(os.environ.get("MF_QUERY_TIMEOUT", "30"))


# ── outcome helpers ───────────────────────────────────────────────────────


def _answered(
    metric: str,
    value: Any,
    dimensions: list[str],
    time_range_used: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "category": "answered",
        "metric": metric,
        "value": value,
        "dimensions": dimensions,
        "time_range": time_range_used,
        "rows": rows,
    }


def _unknown_metric(proposed: list[str]) -> dict[str, Any]:
    return {
        "category": "unknown_metric",
        "message": f"Metrics not found in governed catalog: {proposed}",
        "proposed_metrics": proposed,
    }


def _ambiguous(metrics: list[str]) -> dict[str, Any]:
    return {
        "category": "ambiguous",
        "message": f"Question matched multiple metrics: {metrics}",
        "proposed_metrics": metrics,
    }


def _unsupported_domain(domain: str) -> dict[str, Any]:
    return {
        "category": "unsupported_domain",
        "message": f"Domain '{domain}' is not supported by the governed catalog",
        "domain": domain,
    }


def _system_error(message: str, detail: str = "") -> dict[str, Any]:
    return {
        "category": "system_error",
        "message": message,
        "detail": detail,
    }


def _unsupported_filter(
    computable_metric: str,
    available_dimensions: list[str],
    unsupported_filters: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the ``unknown_metric``/``unsupported_filter`` abstain object.

    Reuses the ``unknown_metric`` category (keeping the five-category contract
    intact) with a discriminating ``reason`` so a caller can tell a fabricated
    metric apart from an ungovernable SCOPE filter. The object is deliberately
    self-explaining: it names the metric it *could* have computed, the governed
    dimensions that DO exist for that metric, and the exact unmatched value(s),
    so the message can show its work rather than emit a blank "no".
    """
    # Human-readable list of the values the model could not govern.
    values = [str(f.get("value")) for f in unsupported_filters if f.get("value")]
    values_str = ", ".join(f"'{v}'" for v in values) or "that constraint"
    first_value = values[0] if values else "that constraint"

    if available_dimensions:
        dims_str = ", ".join(available_dimensions)
        dims_clause = f"{computable_metric} can be broken down by {dims_str}."
    else:
        dims_clause = f"{computable_metric} has no additional breakdown dimensions."

    message = (
        f"I can compute {computable_metric}, but the governed model has no way to "
        f"identify {values_str}. {dims_clause} I don't see any governed value "
        f"matching '{first_value}' — tracking that would be a data-model change."
    )

    return {
        "category": "unknown_metric",
        "reason": "unsupported_filter",
        "computable_metric": computable_metric,
        "available_dimensions": available_dimensions,
        "unsupported_filters": unsupported_filters,
        "proposed_metrics": [computable_metric],
        "message": message,
    }


# ── TR3: HallucinationChecker ─────────────────────────────────────────────


def _check_unknown_metrics(
    metric_names: list[str], catalog: dict[str, Any]
) -> dict[str, Any] | None:
    """Return an ``unknown_metric`` outcome if any proposed metric is not in the catalog.

    Returns ``None`` if all metrics are valid.
    """
    known = {m["name"] for m in catalog.get("metrics", [])}
    unknown = [m for m in metric_names if m not in known]
    if unknown:
        return _unknown_metric(unknown)
    return None


# ── ambiguity check ───────────────────────────────────────────────────────


def _check_ambiguous(metric_names: list[str]) -> dict[str, Any] | None:
    """Return ``ambiguous`` if more than one metric is proposed.

    Returns ``None`` if zero or one metric (single-metric = valid).
    """
    if len(metric_names) > 1:
        return _ambiguous(metric_names)
    return None


# ── TR5: domain check ─────────────────────────────────────────────────────


def _check_domain(
    domain: str | None, catalog: dict[str, Any]
) -> dict[str, Any] | None:
    """Return ``unsupported_domain`` if domain is not in the catalog's domain list.

    Returns ``None`` if the domain is valid or absent (we tolerate missing domain
    by treating it as a non-blocking warning).
    """
    if not domain or domain == "unknown":
        return None  # unknown is a content issue handled by unknown_metric check
    supported = set(catalog.get("domains", []))
    if domain not in supported:
        return _unsupported_domain(domain)
    return None


# ── TR7: server-side dimension validation ─────────────────────────────


def validate_dimensions(
    metric_names: list[str],
    proposed_dims: list[str],
    catalog: dict[str, Any],
) -> list[str]:
    """Filter proposed dimensions to only those valid for the given metrics.

    A dimension is valid if it appears in **any** of the selected metrics'
    ``valid_dimensions`` list.  Returns the filtered list.
    """
    if not proposed_dims:
        return []

    valid_for_metrics: set[str] = set()
    metric_lookup = {m["name"]: m for m in catalog.get("metrics", [])}
    for name in metric_names:
        m = metric_lookup.get(name)
        if m:
            valid_for_metrics.update(m.get("valid_dimensions", []))

    valid = [d for d in proposed_dims if d in valid_for_metrics]
    invalid = [d for d in proposed_dims if d not in valid_for_metrics]
    if invalid:
        logger.info("Dimensions filtered out (invalid for selected metrics): %s", invalid)
    return valid


# ── filter-coverage guard (never confidently wrong) ───────────────────────


def check_filter_coverage(
    metric: str,
    filters: list[dict[str, Any]] | None,
    catalog: dict[str, Any],
) -> dict[str, Any] | None:
    """Abstain when a restrictive SCOPE filter cannot be applied to the query.

    On a governed semantic layer the number is exact, so the only way to be
    wrong is to answer a DIFFERENT question with a real metric. That happens when
    the model asks for a scoped total ("revenue *from marketplace*", "tokens
    billed *to the Customer Success team*") but the restriction is silently
    dropped and an UNSCOPED total is returned as if it were scoped. This guard
    converts that class of confident-wrong answer into a transparent abstention.

    Distinction from ``validate_dimensions``: a ``dimension`` is a BREAKDOWN
    (group-by) — dropping an unexpressible breakdown still leaves the metric's
    TOTAL correct, so those keep answering. A ``filter`` is a restrictive SCOPE
    that CHANGES the number, so a dropped filter yields a wrong number.

    Phase-1 rule (this increment): the MetricFlow command builder emits NO
    ``--where`` push-down, so NO scope filter is ever actually applied to the
    query. Therefore ANY non-empty ``filters`` means the returned total is
    unscoped = a different number → ABSTAIN. The guard keys off "was the scope
    actually applied to the query", NOT merely "is ``field`` a valid dimension":
    a filter naming a perfectly valid catalog dimension still yields a wrong
    answer today because nothing pushes it down.

    Phase-2 seam (DEFERRED — do not build here): when ``build_mf_query_command``
    learns to push expressible filters down as ``--where``, this function should
    partition ``filters`` into pushed vs. residual and abstain only on the
    residual. That is the single place to change; the ``_filter_is_applied``
    predicate below is the seam.

    Parameters
    ----------
    metric
        The single selected metric name (ambiguity is already resolved upstream).
    filters
        The selection payload's ``filters`` list. ``None`` or absent is read as
        ``[]`` (backward-compat with responses that predate the field).
    catalog
        The compact catalog; used to look up the metric's ``valid_dimensions``
        so the abstention can SHOW the governed dimensions that do exist.

    Returns
    -------
    dict or None
        An ``unknown_metric`` / ``unsupported_filter`` abstain object when a
        scope filter cannot be governed, or ``None`` to pass through.
    """
    filters = filters or []
    if not isinstance(filters, list):
        # Defensive: a malformed payload (non-list) is treated as "no usable
        # governed scope" — fail loud toward abstention, never toward a
        # silently-unscoped answer.
        logger.warning("filters payload was not a list (%r) — treating as ungoverned", type(filters))
        filters = []
    if not filters:
        return None  # no scope constraint → the total is the right answer

    # Phase 1: nothing is pushed down, so every filter is unapplied. Every
    # non-empty filter set is therefore an unsupported scope → abstain.
    unsupported = [f for f in filters if not _filter_is_applied(f, catalog)]
    if not unsupported:
        return None  # (unreachable in Phase 1; the Phase-2 pass-through path)

    metric_lookup = {m["name"]: m for m in catalog.get("metrics", [])}
    available_dimensions = metric_lookup.get(metric, {}).get("valid_dimensions", [])

    logger.info(
        "Filter-coverage guard ABSTAIN: metric=%s unsupported_filters=%s",
        metric,
        unsupported,
    )
    return _unsupported_filter(metric, available_dimensions, unsupported)


def _filter_is_applied(filter_obj: dict[str, Any], catalog: dict[str, Any]) -> bool:  # noqa: ARG001
    """Return whether a scope filter is actually pushed down to the mf query.

    Phase-1 seam: there is NO ``--where`` push-down in the query today, so no
    filter is ever applied — this always returns ``False``. Phase 2 replaces the
    body with the real push-down check (is ``field`` an expressible catalog
    dimension AND does the command builder emit it as ``--where``). Keeping the
    predicate isolated means the guard's abstain logic never changes.
    """
    return False


# ── rank / argmax coverage guard (never confidently wrong) ────────────────
#
# The prompt (ai-architect's file) classifies intent and NAMES the dimension in
# a ``rank`` object; THIS code decides rank-vs-abstain and computes the argmax.
# The whole guard mirrors ``check_filter_coverage``: same abstain mechanism
# (reuse the ``unknown_metric`` category with a discriminating ``reason``), same
# "show your work" clarify message, same "fail loud toward abstention" ethos.

# Superlative lexicon for the LEXICAL BACKSTOP. When the model FAILS to emit a
# ``rank`` object but the question is an unmistakable superlative frame, bias to
# ABSTAIN rather than return a grand total dressed up as a winner.
#
# HARD CONSTRAINT: "peak" is deliberately EXCLUDED. It is a metric name
# (``peak_rpm``, ``peak_tpm``) and appears in fixture rows ("quota peak"), so
# treating it as a superlative synonym would false-fire the backstop on a plain
# metric lookup. Do not add it here.
_RANK_LEXICON = [
    "which",
    "most",
    "highest",
    "lowest",
    "largest",
    "smallest",
    "fewest",
    "greatest",
    "top",
    "bottom",
    "maximum",
    "minimum",
    "least",
    "more than any",
    "ranked by",
]
_SUPERLATIVE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _RANK_LEXICON) + r")\b",
    re.IGNORECASE,
)


def _matches_superlative(question: str | None) -> bool:
    """Return whether the question matches a tight superlative frame.

    Word-boundary matching so "top" does not fire on "topic" and "peak" (absent
    from the lexicon by design) never fires at all.
    """
    if not question:
        return False
    return bool(_SUPERLATIVE_RE.search(question))


def _unsupported_argmax(
    computable_metric: str,
    requested_field: str | None,
    available_dimensions: list[str],
    *,
    backstop: bool = False,
) -> dict[str, Any]:
    """Build the ``unknown_metric``/``unsupported_argmax_dimension`` abstain object.

    Mirrors ``_unsupported_filter``: reuses the ``unknown_metric`` category
    (keeping the five-category contract intact) with a discriminating ``reason``
    and a self-explaining message that SHOWS the governed dimensions that DO
    exist, so the clarify message shows its work instead of a blank "no".

    ``backstop`` distinguishes the two abstain paths: a model-emitted rank naming
    an ungoverned dimension (requirement 3) vs. the lexical backstop firing when
    the model emitted no rank at all (requirement 2).
    """
    if available_dimensions:
        dims_str = ", ".join(available_dimensions)
        dims_clause = f"{computable_metric} can be ranked by {dims_str}."
    else:
        dims_clause = f"{computable_metric} has no governed breakdown dimensions to rank by."

    if backstop:
        message = (
            f"That looks like a ranking question, but I couldn't resolve it to a "
            f"governed ranking of {computable_metric}. {dims_clause} Tell me which "
            f"of those to rank by and I'll compute the winner."
        )
    else:
        named = f"'{requested_field}'" if requested_field else "the requested dimension"
        message = (
            f"I can compute {computable_metric}, but I can't rank it by {named} — "
            f"that is not a governed dimension of this metric. {dims_clause} Ranking "
            f"by an ungoverned attribute would be a data-model change."
        )

    return {
        "category": "unknown_metric",
        "reason": "unsupported_argmax_dimension",
        "computable_metric": computable_metric,
        "available_dimensions": available_dimensions,
        "requested_rank_field": requested_field,
        "proposed_metrics": [computable_metric],
        "message": message,
        "backstop": backstop,
    }


def check_rank_coverage(
    metric: str,
    rank: dict[str, Any] | None,
    dimensions: list[str] | None,  # noqa: ARG001 – proposed breakdowns, informational
    catalog: dict[str, Any],
    question: str = "",
) -> dict[str, Any] | None:
    """Decide rank-vs-abstain for a superlative / argmax question.

    On a governed semantic layer the number is exact; the argmax failure mode is
    returning a grand TOTAL as though it were the top row of a ranking. This
    guard converts that class of confident-wrong answer into a transparent
    abstention, exactly like ``check_filter_coverage`` does for scope filters.

    Contract (additive — the pass-through path is byte-for-byte unchanged):

    1. ``rank`` null/absent AND no lexical backstop match → pass through (``None``).
    2. ``rank`` absent but the question matches a tight superlative frame →
       ABSTAIN via the lexical backstop (the model missed an obvious ranking).
    3. ``rank`` present AND ``by_field`` is null OR ∉ the metric's valid
       dimensions → ABSTAIN (``unsupported_argmax_dimension``), showing the
       governed dimensions that DO exist.
    4. ``rank`` present AND ``by_field`` valid → pass through (``None``); the
       caller (``process_question``) injects ``by_field`` into the group-by via
       ``rank_group_by`` and computes the winner via ``apply_argmax`` after the
       query runs. The guard stays a pure decision, mirroring the filter guard.

    Parameters
    ----------
    metric
        The single selected metric name (ambiguity already resolved upstream).
    rank
        The selection payload's ``rank`` object, shaped
        ``{"by_field": <catalog dimension | null>, "direction": "max"|"min"}``.
        ``None`` / absent / falsy means the model proposed no ranking.
    dimensions
        The proposed breakdown dimensions (informational; validity is decided
        against the catalog, not the proposed list).
    catalog
        The compact catalog; used to look up the metric's ``valid_dimensions``.
    question
        The original user question, needed for the lexical backstop (item 2).

    Returns
    -------
    dict or None
        An ``unknown_metric``/``unsupported_argmax_dimension`` abstain object, or
        ``None`` to pass through.
    """
    metric_lookup = {m["name"]: m for m in catalog.get("metrics", [])}
    available_dimensions = metric_lookup.get(metric, {}).get("valid_dimensions", [])

    # ── Case A: the model proposed no ranking. ──
    if not rank:
        if _matches_superlative(question):
            logger.info(
                "Rank-coverage BACKSTOP abstain: metric=%s question=%r", metric, question
            )
            return _unsupported_argmax(metric, None, available_dimensions, backstop=True)
        return None  # additive: byte-for-byte pass-through (the regression guarantee)

    # ── Case B: the model proposed a ranking. ──
    if not isinstance(rank, dict):
        # Defensive: a malformed (non-dict) rank cannot name a field → fail loud
        # toward abstention rather than toward an ungrouped grand total.
        logger.warning("rank payload was not a dict (%r) — abstaining toward safety", type(rank))
        by_field = None
    else:
        by_field = rank.get("by_field")

    if not by_field or by_field not in available_dimensions:
        logger.info(
            "Rank-coverage guard ABSTAIN: metric=%s by_field=%r valid=%s",
            metric,
            by_field,
            available_dimensions,
        )
        return _unsupported_argmax(metric, by_field, available_dimensions)

    return None  # valid rank → caller injects group-by + computes the argmax


def rank_group_by(valid_dims: list[str], rank: dict[str, Any] | None) -> list[str]:
    """Ensure the argmax ``by_field`` is present in the group-by.

    Load-bearing: without the group-by column a valid rank executes UNGROUPED and
    silently regresses to a grand total, so the "winner" would just be the
    overall sum. Returns a new list; unchanged when the field is already present
    or the rank is inactive/malformed.
    """
    if not isinstance(rank, dict):
        return list(valid_dims)
    by_field = rank.get("by_field")
    if by_field and by_field not in valid_dims:
        return [*valid_dims, by_field]
    return list(valid_dims)


def _to_number(value: Any) -> float | None:
    """Coerce a parsed metric cell to a float, or ``None`` if non-numeric.

    MetricFlow cells arrive as strings (possibly comma-grouped); rows that do not
    parse are excluded from the ranking rather than crashing it.
    """
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def apply_argmax(
    rows: list[dict[str, Any]],
    metric: str,
    rank: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, Any]:
    """Sort parsed rows numerically by the metric column and pick the winner.

    ``direction`` "max" → descending (argmax); "min" → ascending (argmin);
    default "max". Non-numeric rows sort to the end so they can never win.

    Returns ``(sorted_rows, winner, value)`` where ``winner`` is ``sorted_rows[0]``
    and ``value`` is the winning row's raw metric value (kept as-is, not the
    float used for sorting, so the surfaced number matches the source cell).
    """
    direction = "max"
    if isinstance(rank, dict):
        direction = str(rank.get("direction") or "max").lower()
    reverse = direction != "min"  # max → descending

    scored = [(r, _to_number(r.get(metric))) for r in rows]
    ranked = sorted(
        (pair for pair in scored if pair[1] is not None),
        key=lambda pair: pair[1],
        reverse=reverse,
    )
    sorted_rows = [r for r, _ in ranked] + [r for r, n in scored if n is None]
    winner = sorted_rows[0] if sorted_rows else None
    value = winner.get(metric) if winner else None
    return sorted_rows, winner, value


# ── TR6: relative time resolution ─────────────────────────────────────────


def resolve_time_range(
    time_str: str | None, time_override: str | None = None
) -> tuple[str | None, str | None]:
    """Resolve a relative time phrase into an absolute ``(start, end)`` ISO date pair.

    ``time_override`` — if set (as ``YYYY-MM-DD`` via the argument or the
    ``TIME_OVERRIDE`` env var) — replaces "now" for demo/testing. The argument
    takes precedence over the env var.

    Returns
    -------
    tuple[str | None, str | None]
        ``(start_iso, end_iso)`` as ``YYYY-MM-DD`` strings, or ``(None, None)``
        when there is no usable time filter.

    Defect #7 — MetricFlow rejects a bare ``metric_time between ...`` ``--where``
    clause (``metric_time`` is not a valid column reference, and the
    ``TimeDimension`` grain rarely matches the metric's aggregation grain). The
    grain-agnostic ``--start-time`` / ``--end-time`` CLI flags are the supported
    path, so this function now yields absolute dates for the command builder to
    pass as those flags rather than a WHERE fragment.
    """
    if not time_str or not time_str.strip():
        return (None, None)

    # determine reference "now"
    override = time_override or os.environ.get("TIME_OVERRIDE")
    if override:
        try:
            now = datetime.date.fromisoformat(override)
        except ValueError:
            logger.warning("Invalid time override '%s', falling back to real clock", override)
            now = datetime.date.today()
    else:
        now = datetime.date.today()

    ts = time_str.strip().lower()

    # ── absolute-date passthrough ──
    # Matches both the legacy WHERE-style form ("metric_time between '2026-01-01'
    # and '2026-01-31'") and the bare form the LLM commonly emits
    # ("between 2025-11-01 and 2025-12-31"), with or without quotes.
    abs_match = re.match(
        r"^(?:metric_time\s+)?between\s+'?(\d{4}-\d{2}-\d{2})'?\s+and\s+'?(\d{4}-\d{2}-\d{2})'?",
        ts,
    )
    if abs_match:
        return (abs_match.group(1), abs_match.group(2))

    # ── relative phrases ────────────────────────────────────────────────
    if ts in ("this week", "current week"):
        start = now - datetime.timedelta(days=now.weekday())  # Monday
        end = start + datetime.timedelta(days=6)
    elif ts in ("last week", "previous week"):
        end = now - datetime.timedelta(days=now.weekday() + 1)  # last Sunday
        start = end - datetime.timedelta(days=6)  # previous Monday
    elif ts in ("this month", "current month"):
        start = now.replace(day=1)
        next_month = now.month % 12 + 1
        year = now.year + (1 if now.month == 12 else 0)
        end = datetime.date(year, next_month, 1) - datetime.timedelta(days=1)
    elif ts in ("last month", "previous month"):
        first_of_this = now.replace(day=1)
        end = first_of_this - datetime.timedelta(days=1)
        start = end.replace(day=1)
    elif ts in ("this quarter", "current quarter"):
        q_start_month = ((now.month - 1) // 3) * 3 + 1
        start = now.replace(month=q_start_month, day=1)
        # first day of next quarter
        q_end_month = q_start_month + 3
        if q_end_month > 12:
            end = datetime.date(now.year + 1, q_end_month - 12, 1) - datetime.timedelta(days=1)
        else:
            end = datetime.date(now.year, q_end_month, 1) - datetime.timedelta(days=1)
    elif ts in ("last quarter", "previous quarter"):
        q_start_month = ((now.month - 1) // 3) * 3 + 1
        # go back one quarter
        prev_q_start = q_start_month - 3
        if prev_q_start < 1:
            start = now.replace(year=now.year - 1, month=prev_q_start + 12, day=1)
        else:
            start = now.replace(month=prev_q_start, day=1)
        # end = day before this quarter start
        this_q_start = now.replace(month=q_start_month, day=1)
        end = this_q_start - datetime.timedelta(days=1)
    elif ts in ("this year", "ytd", "year to date"):
        start = now.replace(month=1, day=1)
        end = now
    elif ts.startswith("last ") and ts.endswith(" days"):
        try:
            n = int(ts.split()[1])
            start = now - datetime.timedelta(days=n)
            end = now
        except (ValueError, IndexError):
            return (None, None)
    else:
        logger.info("Unrecognised time phrase '%s' – no time filter applied", time_str)
        return (None, None)

    # Absolute ISO date pair for MetricFlow --start-time / --end-time flags.
    return (start.isoformat(), end.isoformat())


# ── MetricFlow command builder ────────────────────────────────────────────


def build_mf_query_command(
    metric_names: list[str],
    dimensions: list[str],
    start_time: str | None = None,
    end_time: str | None = None,
) -> list[str]:
    """Build the ``mf query`` command and argument list.

    Parameters
    ----------
    metric_names
        Exactly one metric name for non-ambiguous queries.
    dimensions
        Validated dimension names to group by.
    start_time, end_time
        Absolute ``YYYY-MM-DD`` bounds (Defect #7). Emitted as the
        grain-agnostic ``--start-time`` / ``--end-time`` flags instead of a
        ``--where metric_time between ...`` clause, which MetricFlow rejects.
        Either may be ``None`` to leave that bound open.

    Returns
    -------
    list[str]
        The argv list suitable for ``subprocess.run``.
    """
    if not metric_names:
        msg = "build_mf_query_command called with empty metric_names"
        raise ValueError(msg)

    cmd = ["mf", "query", "--metrics", metric_names[0]]
    cmd.extend(["--group-by", "metric_time"])
    for dim in dimensions:
        cmd.extend(["--group-by", dim])
    if start_time:
        cmd.extend(["--start-time", start_time])
    if end_time:
        cmd.extend(["--end-time", end_time])
    return cmd


# ── MetricFlow execution ──────────────────────────────────────────────────


def execute_mf_query(cmd: list[str]) -> tuple[int, str, str]:
    """Run ``mf query`` as a subprocess and return ``(returncode, stdout, stderr)``."""
    # MetricFlow needs to run from the dbt project directory
    dbt_path = Path(DBT_DIR)
    if not dbt_path.exists():
        return (1, "", f"DBT_DIR {DBT_DIR} does not exist")

    logger.info("Executing: %s (cwd=%s)", " ".join(cmd), dbt_path)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(dbt_path),
            capture_output=True,
            text=True,
            timeout=MF_QUERY_TIMEOUT,
        )
        return (proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return (1, "", f"mf query timed out after {MF_QUERY_TIMEOUT}s")
    except FileNotFoundError:
        return (1, "", "mf command not found – is MetricFlow installed?")
    except Exception as exc:
        return (1, "", str(exc))


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SEPARATOR_RE = re.compile(r"^[\s|+-]*-{2,}[\s|+-]*$")


def parse_mf_output(stdout: str) -> list[dict[str, Any]]:
    """Parse the MetricFlow CLI's whitespace-aligned table into row dicts.

    The ``mf query`` default output looks like::

        ⠋ Initiating query…✔ Success 🦄 - query completed after 0.06 seconds
        metric_time__week      total_net_revenue
        -------------------  -------------------
        2025-10-27T00:00:00              1.8143
        ...

    So this: strips ANSI/carriage-return spinner noise, locates the dashed
    separator line, takes the line above it as the header and the lines below as
    data rows, and splits each on runs of 2+ spaces (columns are space-padded).
    Column keys are the raw MetricFlow headers — note the group-by column is
    grain-suffixed (``metric_time__week``) while the metric column is the bare
    metric name (``total_net_revenue``), so ``row[metric_name]`` resolves.

    Returns ``[]`` for empty / header-only output (TR10: zero rows is still
    ``answered``).
    """
    if not stdout or not stdout.strip():
        return []

    # Drop ANSI escapes and collapse carriage-return progress redraws.
    cleaned = _ANSI_RE.sub("", stdout).replace("\r", "\n")
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    # Find the dashed separator; the header is the line immediately above it.
    sep_idx = next((i for i, ln in enumerate(lines) if _SEPARATOR_RE.match(ln)), None)
    if sep_idx is None or sep_idx == 0:
        return []

    header = re.split(r"\s{2,}", lines[sep_idx - 1].strip())
    rows: list[dict[str, Any]] = []
    for line in lines[sep_idx + 1 :]:
        values = re.split(r"\s{2,}", line.strip())
        if not values or (len(values) == 1 and not values[0]):
            continue
        rows.append(dict(zip(header, values, strict=False)))
    return rows


# ── main routing ──────────────────────────────────────────────────────────


def process_question(
    question: str,
    catalog: dict[str, Any],
    llm_result: dict[str, Any] | None = None,
    time_override: str | None = None,
) -> dict[str, Any]:
    """Route a question through the five-category contract and return the outcome.

    Parameters
    ----------
    question
        The original user question (used for logging).
    catalog
        The compact catalog from ``catalog_builder.build_catalog()``.
    llm_result
        Pre-computed LLM selection, or ``None`` to call the LLM inline.
    time_override
        Override date (YYYY-MM-DD) for relative time resolution (TR6).

    Returns
    -------
    dict
        One of the five outcome shapes.
    """
    # ── 1. Obtain LLM selection ────────────────────────────────────────
    if llm_result is None:
        from . import llm_client  # noqa: PLC0415 – late import avoids circular

        llm_result = llm_client.select_metrics(question, catalog)

    if llm_result is None:
        return _system_error("LLM provider failed to return a response")
    logger.info(
        "LLM result: metrics=%s dims=%s time=%s domain=%s",
        llm_result.get("metrics"),
        llm_result.get("dimensions"),
        llm_result.get("time_range"),
        llm_result.get("domain"),
    )

    # ── 2. Decline routing (classification-driven, safety-biased) ──────
    # The model self-classifies into the five-category contract; the checks
    # below TRUST that signal but override toward a rejection category when the
    # payload contradicts an "answered" claim (fabricated or multiple metrics).
    # A missing/blank classification degrades gracefully to the structural
    # checks (empty / >1 / unknown-name), preserving backward compatibility.
    classification = str(llm_result.get("classification") or "").strip().lower()
    proposed_metrics = llm_result.get("metrics", [])
    domain = llm_result.get("domain")
    supported_domains = set(catalog.get("domains", []))

    # 2a. unsupported_domain — checked FIRST so an out-of-catalog subject
    # (which also carries metrics: []) is not swallowed by the unknown_metric
    # shortcut below. Fires on the model's flag OR on a named domain that is
    # neither supported nor the "unknown" placeholder.
    if classification == "unsupported_domain":
        return _unsupported_domain(domain or "unknown")
    if domain and domain != "unknown" and domain not in supported_domains:
        return _unsupported_domain(domain)

    # 2b. ambiguous — model flagged it, OR it proposed more than one metric.
    if classification == "ambiguous" or len(proposed_metrics) > 1:
        return _ambiguous(proposed_metrics)

    # 2c. unknown_metric — model flagged it, OR proposed nothing, OR proposed a
    # name absent from the governed catalog (TR3 hallucination guard overrides
    # an over-eager "answered" classification).
    if classification == "unknown_metric" or not proposed_metrics:
        return _unknown_metric(proposed_metrics)
    unknown = _check_unknown_metrics(proposed_metrics, catalog)
    if unknown:
        return unknown

    # ── 4. Filter-coverage guard (never confidently wrong) ─────────────
    # A restrictive SCOPE filter that cannot be applied to the query would make
    # us return an UNSCOPED total as if it were scoped — a confident wrong
    # answer. Abstain instead. Runs AFTER unknown/ambiguous (single valid metric
    # is now guaranteed) and BEFORE build/execute (so no wrong query ever runs).
    # ``filters`` absent → read as [] (backward-compat). Breakdowns are handled
    # separately by validate_dimensions and are unaffected.
    filter_abstain = check_filter_coverage(
        proposed_metrics[0], llm_result.get("filters"), catalog
    )
    if filter_abstain:
        return filter_abstain

    # ── 4b. Rank / argmax coverage guard (never confidently wrong) ─────
    # A superlative question ("which model used the most tokens") must not be
    # answered with a grand TOTAL dressed up as the winner. Runs RIGHT AFTER the
    # filter guard and BEFORE build/execute: abstain on an ungoverned rank
    # dimension or on a lexical-backstop miss, so no wrong query ever runs.
    # ``rank`` absent AND no backstop → pass through unchanged (additive).
    rank = llm_result.get("rank")
    rank_abstain = check_rank_coverage(
        proposed_metrics[0], rank, llm_result.get("dimensions", []), catalog, question
    )
    if rank_abstain:
        return rank_abstain

    # ── 5. TR7: validate dimensions ────────────────────────────────────
    proposed_dims = llm_result.get("dimensions", [])
    valid_dims = validate_dimensions(proposed_metrics, proposed_dims, catalog)

    # A valid rank survived the guard: ensure its by_field is in the group-by so
    # the metric is computed PER dimension value, not as one ungrouped total (a
    # missing group-by would silently regress the "winner" to the grand total).
    rank_active = bool(rank)
    if rank_active:
        valid_dims = rank_group_by(valid_dims, rank)

    # ── 6. TR6: time resolution ────────────────────────────────────────
    start_time, end_time = resolve_time_range(llm_result.get("time_range", ""), time_override)
    logger.info(
        "Resolved time: '%s' → start=%s end=%s",
        llm_result.get("time_range"),
        start_time,
        end_time,
    )
    if start_time and end_time:
        time_range_used = f"{start_time} to {end_time}"
    elif start_time:
        time_range_used = f"from {start_time}"
    elif end_time:
        time_range_used = f"through {end_time}"
    else:
        time_range_used = "all available"

    # ── 7. Build and execute MetricFlow query ──────────────────────────
    try:
        cmd = build_mf_query_command(proposed_metrics, valid_dims, start_time, end_time)
    except ValueError as exc:
        return _system_error(str(exc))

    retcode, stdout, stderr = execute_mf_query(cmd)

    if retcode != 0:
        return _system_error(
            "MetricFlow query failed",
            detail=f"exit code {retcode}: {stderr[:500]}",
        )

    # ── 8. Parse results ───────────────────────────────────────────────
    rows = parse_mf_output(stdout)

    # 8b. Argmax: for a valid rank, sort numerically by the metric column and
    # surface the winner (rows[0] + an ``argmax`` field). THIS code computes the
    # ranking; the prompt only named the dimension.
    if rank_active:
        sorted_rows, winner, argmax_value = apply_argmax(rows, proposed_metrics[0], rank)
        result = _answered(
            metric=proposed_metrics[0],
            value=argmax_value,
            dimensions=valid_dims,
            time_range_used=time_range_used,
            rows=sorted_rows,
        )
        result["argmax"] = winner
        return result

    # TR10: zero rows is still answered
    value = rows[0].get(proposed_metrics[0], "N/A") if rows else None

    return _answered(
        metric=proposed_metrics[0],
        value=value,
        dimensions=valid_dims,
        time_range_used=time_range_used,
        rows=rows,
    )
