"""
Builds a compact LLM-facing catalog from the dbt semantic manifest.

Reads dbt/target/semantic_manifest.json and cross-references metric names with
docs/10.METRIC_DICTIONARY.csv for domain tags. Valid dimensions are derived from
the semantic manifest so the app sees fresh dbt/MetricFlow metadata after
``dbt parse``; the generated YAML catalog is kept only as a fallback.

Output is a dict with keys ``domains``, ``metrics``, ``dimensions``.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── configurable paths (relative to conversational-bi/ CWD) ──────────────
MANIFEST_PATH = os.environ.get(
    "MF_MANIFEST_PATH", "../dbt/target/semantic_manifest.json"
)
DICTIONARY_PATH = os.environ.get(
    "MF_DICTIONARY_PATH", "../docs/10.METRIC_DICTIONARY.csv"
)
YAML_CATALOG_PATH = os.environ.get(
    "MF_YAML_CATALOG_PATH", "../dbt/target/catalog_for_llm.yaml"
)

# ── helpers ───────────────────────────────────────────────────────────────


def _load_metric_domain_map() -> dict[str, str]:
    """Return ``{metric_name: domain}`` from the metric dictionary CSV."""
    domain_map: dict[str, str] = {}
    path = Path(DICTIONARY_PATH)
    if not path.exists():
        logger.warning("Metric dictionary not found at %s", path)
        return domain_map
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("metric_name", "").strip()
            domain = row.get("domain", "").strip()
            if name and domain:
                domain_map[name] = domain
    logger.info("Domain map: %d entries loaded from CSV", len(domain_map))
    return domain_map


# Governance markers: a dictionary row whose status/approved_status contains any
# of these tokens is a retired variant and must NOT be offered to the LLM.
_RETIRED_STATUS_TOKENS = ("deprecat", "absorb", "retired", "superseded")


def _load_approved_metric_names() -> set[str]:
    """Return the governed allowlist of metric names from the dictionary CSV.

    The metric dictionary (``docs/10.METRIC_DICTIONARY.csv``) is the single
    source of truth for which metrics are canonical vs. retired. Every listed
    ``metric_name`` is approved unless a status/approved_status column explicitly
    marks it deprecated/absorbed. Any metric in the semantic manifest that is
    *absent* from this allowlist is a retired variant (an absorbed or renamed
    name) and is excluded from the catalog served to the model.

    Returns an empty set only when the dictionary is missing/unreadable; callers
    treat an empty allowlist as "governance unavailable" and skip filtering
    rather than serving zero metrics.
    """
    approved: set[str] = set()
    path = Path(DICTIONARY_PATH)
    if not path.exists():
        logger.warning(
            "Metric dictionary not found at %s – governance allowlist unavailable",
            path,
        )
        return approved
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            name = row.get("metric_name", "").strip()
            if not name:
                continue
            status = f"{row.get('status', '')} {row.get('approved_status', '')}".lower()
            if any(tok in status for tok in _RETIRED_STATUS_TOKENS):
                continue
            approved.add(name)
    logger.info("Governance allowlist: %d approved metric names loaded", len(approved))
    return approved


def _build_measure_agg_map(manifest: dict[str, Any]) -> dict[str, str]:
    """Return ``{measure_name: agg}`` across every semantic model.

    The aggregation type (``sum``/``average``/``count_distinct``/…) is the
    governed signal the investigation loop's **additivity gate** reads: only
    ``sum``-aggregated measures have per-member deltas that add up to the total
    delta, so only they may claim dimensional *contribution*. Ratios and averages
    (e.g. ``error_rate`` → ``error_rate_pct`` agg ``average``) may report values
    but never "X drove it" (design §146).
    """
    agg_map: dict[str, str] = {}
    for sm in manifest.get("semantic_models", []):
        for meas in sm.get("measures", []):
            name = meas.get("name")
            agg = meas.get("agg")
            if name and agg:
                agg_map[name] = str(agg)
    return agg_map


def _metric_agg(metric: dict[str, Any], measure_agg: dict[str, str]) -> str | None:
    """Return the effective aggregation for a metric, or ``None`` if not additive-simple.

    A ``simple`` metric wraps exactly one input measure; its aggregation IS that
    measure's ``agg``. ``ratio``/``derived``/``cumulative`` metrics have no single
    additive aggregation (their per-member deltas do not sum), so they return
    ``None`` — read by the loop as non-additive.
    """
    if metric.get("type") != "simple":
        return None
    tp = metric.get("type_params", {}) or {}
    measures = tp.get("measures") or tp.get("input_measures") or []
    names = [m.get("name") for m in measures if isinstance(m, dict)]
    if len(names) != 1 or not names[0]:
        return None
    return measure_agg.get(names[0])


def _load_dimension_catalog() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Load full dimension definitions and per-metric valid dimensions from the YAML catalog.

    Returns
    -------
    (dimensions_list, metric_dims_map)
        ``dimensions_list``: every known dimension ``{name, type, description}``.
        ``metric_dims_map``: ``{metric_name: [valid_dimension_names]}``.
    """
    dims_list: list[dict[str, Any]] = []
    metric_dims: dict[str, list[str]] = {}
    path = Path(YAML_CATALOG_PATH)
    if not path.exists():
        logger.warning("YAML catalog not found at %s – dimension info unavailable", path)
        return dims_list, metric_dims

    try:
        import yaml  # noqa: PLC0415 – optional

        with open(path) as f:
            data = yaml.safe_load(f)

        dims_list = data.get("dimensions", [])
        for m in data.get("metrics", []):
            name = m.get("name")
            dims = m.get("valid_dimensions", [])
            if name:
                metric_dims[name] = dims

        logger.info(
            "Loaded %d dimensions and %d metric→dimension mappings from YAML",
            len(dims_list),
            len(metric_dims),
        )
    except ImportError:
        logger.warning("PyYAML not available – YAML catalog skipped")
    except Exception:
        logger.exception("Failed to load YAML catalog")

    return dims_list, metric_dims


_SURROGATE_FACT_ENTITIES = {"revenue_id", "usage_id", "quota_week_id"}


def _metric_measure_names(metric: dict[str, Any]) -> list[str]:
    """Return the measure names a metric depends on."""
    tp = metric.get("type_params", {}) or {}
    measures = tp.get("input_measures") or tp.get("measures") or []
    names: list[str] = []
    for measure in measures:
        if isinstance(measure, dict) and measure.get("name"):
            names.append(str(measure["name"]))
    return names


def _semantic_entity_names(semantic_model: dict[str, Any]) -> list[str]:
    """Return declared entity names for a semantic model."""
    return [
        str(entity["name"])
        for entity in semantic_model.get("entities", [])
        if entity.get("name")
    ]


def _primary_entity_name(semantic_model: dict[str, Any]) -> str | None:
    """Return the primary entity name, if the semantic model declares one."""
    for entity in semantic_model.get("entities", []):
        if entity.get("type") == "primary" and entity.get("name"):
            return str(entity["name"])
    return None


def _semantic_dimension_names(semantic_model: dict[str, Any]) -> list[str]:
    """Return non-time dimension names declared directly on a semantic model."""
    names: list[str] = []
    for dimension in semantic_model.get("dimensions", []):
        if dimension.get("type") == "time":
            continue
        name = dimension.get("name")
        if name:
            names.append(str(name))
    return names


def _build_dimension_catalog_from_manifest(
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """Derive LLM-facing valid dimensions from the fresh semantic manifest.

    MetricFlow exposes business entity attributes as ``entity__dimension`` while
    fact-local degenerate dimensions stay bare. This mirrors the command names
    users can pass to ``mf query --group-by`` and avoids the stale
    ``catalog_for_llm.yaml`` problem after a semantic-model re-point.
    """
    entity_dimensions: dict[str, list[str]] = {}
    measure_models: dict[str, list[dict[str, Any]]] = {}

    for semantic_model in manifest.get("semantic_models", []):
        primary = _primary_entity_name(semantic_model)
        local_dims = _semantic_dimension_names(semantic_model)

        # Only measure-less semantic models are conformed dimensions. Do not let
        # other metric-bearing rollups become implicit dimension sources for the
        # re-pointed facts.
        if primary and not semantic_model.get("measures"):
            entity_dimensions.setdefault(primary, [])
            entity_dimensions[primary].extend(local_dims)

        for measure in semantic_model.get("measures", []):
            name = measure.get("name")
            if name:
                measure_models.setdefault(str(name), []).append(semantic_model)

    metric_dims: dict[str, list[str]] = {}
    all_dimension_names: set[str] = set()

    for metric in manifest.get("metrics", []):
        metric_name = metric.get("name")
        if not metric_name:
            continue

        dims: list[str] = []
        for measure_name in _metric_measure_names(metric):
            for semantic_model in measure_models.get(measure_name, []):
                primary = _primary_entity_name(semantic_model)

                for entity_name in _semantic_entity_names(semantic_model):
                    if entity_name not in _SURROGATE_FACT_ENTITIES:
                        dims.append(entity_name)
                    for entity_dim in entity_dimensions.get(entity_name, []):
                        dims.append(f"{entity_name}__{entity_dim}")

                for local_dim in _semantic_dimension_names(semantic_model):
                    if primary:
                        dims.append(f"{primary}__{local_dim}")
                    else:
                        dims.append(local_dim)

        deduped = list(dict.fromkeys(dims))
        metric_dims[str(metric_name)] = deduped
        all_dimension_names.update(deduped)

    dimensions = [{"name": name, "type": "categorical"} for name in sorted(all_dimension_names)]
    return dimensions, metric_dims


# ── public API ────────────────────────────────────────────────────────────


def build_catalog(
    manifest_path: str | None = None,
    dictionary_path: str | None = None,
    yaml_catalog_path: str | None = None,
) -> dict[str, Any]:
    """Build and return the compact catalog dict.

    Parameters
    ----------
    manifest_path
        Override for the semantic manifest JSON location.
    dictionary_path
        Override for the metric dictionary CSV location.
    yaml_catalog_path
        Override for the pre-built YAML catalog location.

    Returns
    -------
    dict
        ``{"domains": [...], "metrics": [...], "dimensions": [...]}``
    """
    mp = Path(manifest_path or MANIFEST_PATH)
    if not mp.exists():
        raise FileNotFoundError(
            f"Semantic manifest not found at {mp.resolve()}. "
            "Run ``dbt parse`` first."
        )

    with open(mp) as f:
        manifest = json.load(f)

    # cross-reference domain tags from CSV
    domain_map = _load_metric_domain_map()

    # governance allowlist: only canonical (non-retired) metrics are served
    approved_names = _load_approved_metric_names()
    governance_active = bool(approved_names)
    if not governance_active:
        logger.warning(
            "Governance allowlist empty – serving ALL manifest metrics unfiltered. "
            "Retired/absorbed variants may be exposed to the model."
        )

    # dimension info from the fresh manifest; YAML stays a fallback for older
    # target directories that lack enough manifest detail.
    yaml_dimensions, yaml_metric_dims = _load_dimension_catalog()
    manifest_dimensions, manifest_metric_dims = _build_dimension_catalog_from_manifest(manifest)
    all_dimensions = manifest_dimensions or yaml_dimensions
    metric_dims = {**yaml_metric_dims, **manifest_metric_dims}

    # per-measure aggregation map (drives the loop's additivity gate)
    measure_agg = _build_measure_agg_map(manifest)

    # ── build metrics list ────────────────────────────────────────────
    domain_set: set[str] = set()
    metrics: list[dict[str, Any]] = []
    excluded: list[str] = []

    for m in manifest.get("metrics", []):
        name: str = m.get("name", "")
        if not name:
            continue

        # governance filter: skip metrics absent from the approved allowlist
        # (absorbed/renamed/deprecated variants). Skipped only when governance
        # is active so a missing dictionary never yields an empty catalog.
        if governance_active and name not in approved_names:
            excluded.append(name)
            continue

        # domain: CSV wins, then manifest meta, then "unknown"
        domain = domain_map.get(name) or m.get("config", {}).get("meta", {}).get("domain") or "unknown"  # type: ignore[union-attr]
        domain = str(domain)
        domain_set.add(domain)

        metrics.append(
            {
                "name": name,
                "label": m.get("label", name),
                "description": m.get("description", ""),
                "type": m.get("type", "simple"),
                # Governed aggregation of the wrapped measure (``sum`` = additive),
                # or ``None`` for ratio/derived metrics. Read by the investigation
                # loop's additivity gate; additive to the LLM catalog (ignored by
                # clients that don't know the key).
                "agg": _metric_agg(m, measure_agg),
                "domain": domain,
                "valid_dimensions": metric_dims.get(name, []),
            }
        )

    metrics.sort(key=lambda x: x["name"])
    domains = sorted(d for d in domain_set if d != "unknown")
    if "unknown" in domain_set:
        domains.append("unknown")

    catalog = {"domains": domains, "metrics": metrics, "dimensions": all_dimensions}

    logger.info(
        "Catalog built: %d domains, %d metrics, %d dimensions",
        len(domains),
        len(metrics),
        len(all_dimensions),
    )
    if excluded:
        logger.info(
            "Governance filter excluded %d retired variant(s) from LLM catalog: %s",
            len(excluded),
            ", ".join(sorted(excluded)),
        )
    return catalog


def catalog_dimension_names(catalog: dict[str, Any]) -> set[str]:
    """Return a set of every valid dimension name across the catalog."""
    names: set[str] = set()
    for d in catalog.get("dimensions", []):
        name = d.get("name")
        if name:
            names.add(name)
    # also collect per-metric valid_dimensions
    for m in catalog.get("metrics", []):
        names.update(m.get("valid_dimensions", []))
    return names


def domain_metric_names(catalog: dict[str, Any]) -> dict[str, list[str]]:
    """Return ``{domain: [metric_name, ...]}``."""
    result: dict[str, list[str]] = {}
    for m in catalog.get("metrics", []):
        result.setdefault(m["domain"], []).append(m["name"])
    return result
