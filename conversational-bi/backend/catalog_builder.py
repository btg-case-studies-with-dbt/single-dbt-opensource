"""
Builds a compact LLM-facing catalog from the dbt semantic manifest.

Reads dbt/target/semantic_manifest.json, cross-references metric names with
docs/10.METRIC_DICTIONARY.csv for domain tags (the generated YAML has stale
``domain: unknown`` for many metrics).  Also reads the generated YAML catalog
for valid-dimension and valid-grain information per metric — that data lives
only in the YAML, not in the raw manifest.

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

    # dimension info from YAML catalog
    all_dimensions, metric_dims = _load_dimension_catalog()

    # ── build metrics list ────────────────────────────────────────────
    domain_set: set[str] = set()
    metrics: list[dict[str, Any]] = []

    for m in manifest.get("metrics", []):
        name: str = m.get("name", "")
        if not name:
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
