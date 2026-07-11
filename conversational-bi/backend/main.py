"""
FastAPI application for the Governed Metric Execution Architecture.

Endpoints
---------
``GET  /``          — redirect to the static frontend (``/frontend/``)
``GET  /info``      — API info (service metadata JSON)
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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

# Load .env into os.environ BEFORE any module-level env reads (OTEL_ENABLED at
# line 85 below) or env-reading imports (litellm_gateway builds config from env;
# llm_client reads LLM_PROVIDER / OLLAMA_MODEL at its — late — import).
from dotenv import load_dotenv

load_dotenv()

from . import catalog_builder  # noqa: E402
from . import litellm_gateway  # noqa: E402
from .guardrails import ContentFilter, PIIRedactor  # noqa: E402

# ── guardrails ─────────────────────────────────────────────────────────────
_pii_redactor = PIIRedactor()
_content_filter = ContentFilter()

# ── LiteLLM config ─────────────────────────────────────────────────────────
LITELLM_CONFIG: litellm_gateway.LiteLLMConfig | None = None

# ── investigation loop kill-switch (TR12.8e rollback mechanism) ──────────────
# When false, every /query reverts to today's single-shot shape (plain lookups
# and investigative questions alike get investigation.status:"not_investigated").
# This is the instant rollback for the one-way-door contract extension: flip the
# env var and restart to disable the loop without touching client contracts.
INVESTIGATION_ENABLED = os.environ.get("INVESTIGATION_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)

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

# ── OpenTelemetry (gated by OTEL_ENABLED=true) ────────────────────────────

_tracer: trace.Tracer | None = None

if os.environ.get("OTEL_ENABLED", "").lower() in ("true", "1", "yes"):
    resource = Resource(attributes={SERVICE_NAME: "conversational-bi"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    _tracer = trace.get_tracer(__name__)
    logger.info("OpenTelemetry instrumentation enabled")
else:
    logger.info("OpenTelemetry disabled (set OTEL_ENABLED=true to enable)")


# ── startup state ─────────────────────────────────────────────────────────


@app.on_event("startup")
async def _startup() -> None:
    """Load catalog and ensure evidence directory exists on startup."""
    logger.info("Starting %s v%s", APP_TITLE, APP_VERSION)

    # ensure evidence directory exists
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Evidence log: %s", EVIDENCE_LOG)

    global LITELLM_CONFIG
    LITELLM_CONFIG = litellm_gateway.LiteLLMConfig()
    logger.info(
        "LiteLLM gateway config: primary=%s/%s fallback=%s/%s",
        LITELLM_CONFIG.primary_provider,
        LITELLM_CONFIG.primary_model,
        LITELLM_CONFIG.fallback_provider or "(none)",
        LITELLM_CONFIG.fallback_model or "(none)",
    )

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


# ── noop context manager for when OTEL is disabled ────────────────────────


class _NoopSpan:
    """Stand-in for an OpenTelemetry span when OTEL is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ANN401
        pass

    def __enter__(self) -> _NoopSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoopTracer:
    """Stand-in for an OpenTelemetry tracer when OTEL is disabled.

    Exposes ``start_as_current_span`` so ``with tracer.start_as_current_span(...)``
    works identically to the real tracer; it yields a ``_NoopSpan`` (itself a
    context manager) that the downstream ``isinstance(span, _NoopSpan)`` guard
    recognises and skips real span-attribute writes for.
    """

    def start_as_current_span(self, name: str) -> _NoopSpan:  # noqa: ARG002
        return _NoopSpan()


_noop_tracer = _NoopTracer()


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
async def root() -> RedirectResponse:
    """Redirect the base URL to the static frontend SPA."""
    return RedirectResponse(url="/frontend/", status_code=307)


@app.get("/info")
async def info() -> dict[str, Any]:
    """API info — returns metadata about the service."""
    return {
        "service": APP_TITLE,
        "version": APP_VERSION,
        "endpoints": {
            "/": "redirect to the frontend (/frontend/)",
            "/info": "this info",
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

    # ── guardrail 1: PII redaction ──────────────────────────────────────
    question = _pii_redactor.redact(question)

    # ── guardrail 2: content filter ─────────────────────────────────────
    blocked, reason = _content_filter.check(question)
    if blocked:
        return {
            "category": "system_error",
            "message": "Request blocked by content filter",
            "detail": reason,
        }

    # import llm client, query translator, and investigation orchestrator
    # (late import for clean startup)
    from . import agent_graph, llm_client  # noqa: PLC0415

    start = time.monotonic()

    tracer = _tracer or _noop_tracer
    with tracer.start_as_current_span("query") as span:  # type: ignore[union-attr]
        # Route to LiteLLM proxy or native llm_client
        config_provider = (provider or os.environ.get("LLM_PROVIDER", "ollama")).lower()

        if config_provider == "litellm":
            proxy = litellm_gateway.LiteLLMProxy(config=LITELLM_CONFIG)
            llm_result = proxy.select_metrics(
                question=question,
                catalog=app.state.catalog,
                provider=provider,
                model=model,
            )
        else:
            # get LLM selection via native client (default path)
            _native_default_model = {
                "openai": llm_client.DEFAULT_OPENAI_MODEL,
                "anthropic": llm_client.DEFAULT_ANTHROPIC_MODEL,
            }.get(config_provider, llm_client.DEFAULT_OLLAMA_MODEL)
            logger.info(
                "Query routed to native LLM client: provider=%s model=%s",
                config_provider,
                model or _native_default_model,
            )
            llm_result = llm_client.select_metrics(
                question=question,
                catalog=app.state.catalog,
                provider=provider,
                model=model,
            )

        # process question through the five-category router, then the intent
        # gate: investigative + answered runs the bounded investigation loop;
        # everything else keeps the single-shot shape (Decision 1 = A). The base
        # answer is the guaranteed floor and is never regressed by investigation.
        outcome = agent_graph.run_query(
            question=question,
            catalog=app.state.catalog,
            llm_result=llm_result,
            time_override=time_override,
            investigation_enabled=INVESTIGATION_ENABLED,
        )
        elapsed = time.monotonic() - start

        # ── operability: surface investigation health (3 a.m. readability) ──
        investigation = outcome.get("investigation") or {}
        inv_status = investigation.get("status")
        inv_steps = investigation.get("steps_taken")
        inv_stopped = investigation.get("stopped_reason")
        inv_evidence_count = len(investigation.get("evidence", []) or [])
        # A partial/latency/error investigation is the on-call signal: the floor
        # answer stood, but warranted evidence is missing — log it loud (WARNING)
        # so a spike is greppable without turning on debug tracing.
        if inv_status == "partial":
            logger.warning(
                "Investigation PARTIAL: metric=%s stopped_reason=%s steps=%s evidence=%d",
                outcome.get("metric"),
                inv_stopped,
                inv_steps,
                inv_evidence_count,
            )
        elif inv_status == "investigated":
            logger.info(
                "Investigation complete: metric=%s stopped_reason=%s steps=%s evidence=%d",
                outcome.get("metric"),
                inv_stopped,
                inv_steps,
                inv_evidence_count,
            )

        # span attributes
        if hasattr(span, "set_attribute") and not isinstance(span, _NoopSpan):
            span.set_attribute("app.question.length", len(question))
            span.set_attribute("app.question.provider", config_provider)
            span.set_attribute("app.question.category", outcome["category"])
            span.set_attribute("app.question.elapsed_seconds", round(elapsed, 3))
            span.set_attribute("app.investigation.status", str(inv_status))
            span.set_attribute("app.investigation.steps", int(inv_steps or 0))
            span.set_attribute("app.investigation.evidence_count", inv_evidence_count)

        # TR9: structured audit log (PII-redacted)
        audit_record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": round(elapsed, 3),
            "question": _pii_redactor.redact(question),
            "category": outcome["category"],
            "metric": outcome.get("metric"),
            "dimensions": outcome.get("dimensions"),
            "time_range": outcome.get("time_range"),
            "domain": llm_result.get("domain") if llm_result else None,
            "investigation_status": inv_status,
            "investigation_steps": inv_steps,
            "investigation_stopped_reason": inv_stopped,
            "investigation_evidence_count": inv_evidence_count,
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
