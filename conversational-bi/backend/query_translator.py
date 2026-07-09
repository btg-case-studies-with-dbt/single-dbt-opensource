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


# ── TR6: relative time resolution ─────────────────────────────────────────


def resolve_time_range(
    time_str: str | None, time_override: str | None = None
) -> str:
    """Resolve a relative time phrase against the current UTC clock.

    ``time_override`` — if set (as ``YYYY-MM-DD`` or ISO date via the
    ``TIME_OVERRIDE`` env var) — replaces "now" for demo/testing.

    Returns a MetricFlow-compatible ``WHERE`` clause fragment or empty string.
    """
    if not time_str or not time_str.strip():
        return ""

    # determine reference "now"
    override = time_override or os.environ.get("TIME_OVERRIDE")
    if override:
        try:
            now = datetime.date.fromisoformat(override)
        except ValueError:
            logger.warning("Invalid TIME_OVERRIDE '%s', falling back to real clock", override)
            now = datetime.date.today()
    else:
        now = datetime.date.today()

    ts = time_str.strip().lower()

    # ── absolute-date passthrough (e.g. "metric_time between '2026-01-01' and '2026-01-31'") ──
    if re.match(r"^metric_time\s+between\s+", ts):
        return ts

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
            return ""
    else:
        logger.info("Unrecognised time phrase '%s' – leaving as-is", time_str)
        return time_str

    # Build MetricFlow WHERE clause (ISO date format)
    return f"metric_time between '{start.isoformat()}' and '{end.isoformat()}'"


# ── MetricFlow command builder ────────────────────────────────────────────


def build_mf_query_command(
    metric_names: list[str],
    dimensions: list[str],
    time_where_clause: str,
) -> list[str]:
    """Build the ``mf query`` command and argument list.

    Parameters
    ----------
    metric_names
        Exactly one metric name for non-ambiguous queries.
    dimensions
        Validated dimension names to group by.
    time_where_clause
        A WHERE clause fragment (e.g. ``"metric_time between '...' and '...'"``)
        or empty string.

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
    if time_where_clause:
        cmd.extend(["--where", time_where_clause])
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


def parse_mf_output(stdout: str) -> list[dict[str, Any]]:
    """Parse MetricFlow tabular output into a list of row dicts.

    Currently handles CSV output (``--format csv``).  Falls back to splitting
    on whitespace for other formats.
    """
    if not stdout.strip():
        return []

    lines = stdout.strip().splitlines()
    if len(lines) < 2:
        return []

    # assume CSV header + rows
    header = [h.strip() for h in lines[0].split(",")]
    rows: list[dict[str, Any]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = [v.strip() for v in line.split(",")]
        row = dict(zip(header, values, strict=False))
        rows.append(row)
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

    # ── 2. TR3: unknown metrics ────────────────────────────────────────
    proposed_metrics = llm_result.get("metrics", [])
    if not proposed_metrics:
        return _unknown_metric([])

    unknown = _check_unknown_metrics(proposed_metrics, catalog)
    if unknown:
        return unknown

    # ── 3. Ambiguity check ─────────────────────────────────────────────
    ambiguous = _check_ambiguous(proposed_metrics)
    if ambiguous:
        return ambiguous

    # ── 4. TR5: domain check ───────────────────────────────────────────
    domain_check = _check_domain(llm_result.get("domain"), catalog)
    if domain_check:
        return domain_check

    # ── 5. TR7: validate dimensions ────────────────────────────────────
    proposed_dims = llm_result.get("dimensions", [])
    valid_dims = validate_dimensions(proposed_metrics, proposed_dims, catalog)

    # ── 6. TR6: time resolution ────────────────────────────────────────
    time_clause = resolve_time_range(llm_result.get("time_range", ""), time_override)
    logger.info("Resolved time: '%s' → '%s'", llm_result.get("time_range"), time_clause)

    # ── 7. Build and execute MetricFlow query ──────────────────────────
    try:
        cmd = build_mf_query_command(proposed_metrics, valid_dims, time_clause)
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
    # TR10: zero rows is still answered
    value = rows[0].get(proposed_metrics[0], "N/A") if rows else None

    return _answered(
        metric=proposed_metrics[0],
        value=value,
        dimensions=valid_dims,
        time_range_used=time_clause,
        rows=rows,
    )
