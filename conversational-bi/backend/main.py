"""
FastAPI application for the Governed Metric Execution Architecture.

Endpoints
---------
``GET  /``          — API info
``GET  /health``    — health check
``GET  /catalog``   — compact metric catalog (JSON)
``POST /query``     — submit a natural-language question
``GET  /frontend/*``— static frontend
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import catalog_builder

# ── logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── evidence logging (JSON Lines to evidence/query_log.jsonl) ─────────────
EVIDENCE_DIR = Path(__file__).resolve().parents[1] / "evidence"
EVIDENCE_LOG = EVIDENCE_DIR / "query_log.jsonl"

# ── app metadata ──────────────────────────────────────────────────────────
APP_TITLE = "Governed Metric Execution Architecture — Conversational BI"
APP_VERSION = "0.1.0"
DESCRIPTION = """
Five-category question-answering over governed MetricFlow metrics.

Categories: ``answered``, ``unknown_metric``, ``ambiguous``,
``unsupported_domain``, ``system_error``.
"""

# ── app factory ───────────────────────────────────────────────────────────

app = FastAPI(title=APP_TITLE, version=APP_VERSION, description=DESCRIPTION)

# ── CORS ──────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── startup state ─────────────────────────────────────────────────────────


@app.on_event("startup")
async def _startup() -> None:
    """Load catalog and ensure evidence directory exists on startup."""
    logger.info("Starting %s v%s", APP_TITLE, APP_VERSION)

    # ensure evidence directory exists
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Evidence log: %s", EVIDENCE_LOG)

    # preload catalog into app.state
    try:
        app.state.catalog = catalog_builder.build_catalog()
        logger.info(
            "Catalog loaded: %d domains, %d metrics, %d dimensions",
            len(app.state.catalog["domains"]),
            len(app.state.catalog["metrics"]),
            len(app.state.catalog["dimensions"]),
        )
    except FileNotFoundError as exc:
        logger.error("Catalog not available at startup: %s", exc)
        app.state.catalog = {"domains": [], "metrics": [], "dimensions": []}


# ── audit log helper ──────────────────────────────────────────────────────


def _write_audit_log(record: dict[str, Any]) -> None:
    """Append a JSON Line to the evidence log."""
    try:
        with open(EVIDENCE_LOG, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:
        logger.exception("Failed to write audit log")


# ── health checks ─────────────────────────────────────────────────────────


def _check_mf_cli() -> bool:
    """Return True if the ``mf`` CLI is available."""
    try:
        result = subprocess.run(
            ["mf", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── endpoints ─────────────────────────────────────────────────────────────


@app.get("/")
async def root() -> dict[str, Any]:
    """API root — returns info about the service."""
    return {
        "service": APP_TITLE,
        "version": APP_VERSION,
        "endpoints": {
            "/": "this info",
            "/health": "health check",
            "/catalog": "compact metric catalog (no LLM call)",
            "/query": "submit question (POST)",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check — verifies catalog is loaded and mf CLI is present."""
    catalog_loaded = bool(app.state.catalog.get("metrics"))
    mf_ok = _check_mf_cli()

    status_code = 200 if catalog_loaded and mf_ok else 503
    body: dict[str, Any] = {
        "status": "healthy" if status_code == 200 else "degraded",
        "catalog_loaded": catalog_loaded,
        "catalog_metrics_count": len(app.state.catalog.get("metrics", [])),
        "mf_cli_available": mf_ok,
    }
    return JSONResponse(content=body, status_code=status_code)


@app.get("/catalog")
async def catalog() -> dict[str, Any]:
    """Return the compact metric catalog (no LLM call)."""
    return app.state.catalog


@app.post("/query")
async def query(request: Request) -> dict[str, Any]:
    """Accept a natural-language question and return a five-category response.

    Request body (JSON)::

        {
            "question": "What was total net revenue last week?",
            "provider": "ollama",          // optional
            "model": "llama3.2",           // optional
            "time_override": "2026-07-08"  // optional, YYYY-MM-DD
        }
    """
    body = await request.json()
    question: str = (body.get("question") or "").strip()
    provider: str | None = body.get("provider")
    model: str | None = body.get("model")
    time_override: str | None = body.get("time_override")

    if not question:
        raise HTTPException(status_code=422, detail="'question' field is required")

    # import llm client and query translator (late import for clean startup)
    from . import llm_client, query_translator  # noqa: PLC0415

    start = time.monotonic()

    # get LLM selection
    llm_result = llm_client.select_metrics(
        question=question,
        catalog=app.state.catalog,
        provider=provider,
        model=model,
    )

    # process question through five-category router
    outcome = query_translator.process_question(
        question=question,
        catalog=app.state.catalog,
        llm_result=llm_result,
        time_override=time_override,
    )
    elapsed = time.monotonic() - start

    # TR9: structured audit log
    audit_record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 3),
        "question": question,
        "category": outcome["category"],
        "metric": outcome.get("metric"),
        "dimensions": outcome.get("dimensions"),
        "time_range": outcome.get("time_range"),
        "domain": llm_result.get("domain") if llm_result else None,
    }
    _write_audit_log(audit_record)

    outcome["elapsed_seconds"] = round(elapsed, 3)
    return outcome


# ── static frontend mount ──────────────────────────────────────────────────

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    logger.info("Frontend mounted from %s", frontend_dir)
else:
    logger.warning("Frontend directory not found at %s — /frontend will 404", frontend_dir)

# ── direct run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
