"""
LlamaIndex-based evidence retriever for support-ticket lookup.

Provides a ``EvidenceRetriever`` class backed by an in-memory
``SimpleDocumentStore`` + keyword-table index (extract-then-match keyword
search).  Ships with three synthetic support-ticket fixtures.

Usage::

    retriever = EvidenceRetriever()
    results = retriever.retrieve("login failure", {"region": "us-east-1"})
"""

from __future__ import annotations

import logging
from typing import Any

from llama_index.core import Document, SimpleKeywordTableIndex
from llama_index.core.storage.docstore import SimpleDocumentStore

logger = logging.getLogger(__name__)

# ── synthetic fixture ──────────────────────────────────────────────────────

FIXTURE_TICKETS: list[dict[str, str]] = [
    {
        "id": "TKT-001",
        "account_id": "ACME-1234",
        "region": "us-east-1",
        "date": "2026-07-01",
        "severity": "HIGH",
        "topic": "login_failure",
        "summary": "User unable to log in via SSO; SAML assertion rejected with "
        "'invalid audience' error. Auth0 logs confirm mismatch between "
        "configured Entity ID and the SP Assertion Consumer Service URL.",
    },
    {
        "id": "TKT-002",
        "account_id": "GLOBEX-5678",
        "region": "eu-west-1",
        "date": "2026-07-03",
        "severity": "MEDIUM",
        "topic": "data_latency",
        "summary": "Dashboard refresh stalled for 47 minutes. The hourly "
        "ETL pipeline completed but the materialized view was not "
        "rebuilt due to a lock contention issue in Redshift. "
        "Manually re-ran REFRESH MATERIALIZED VIEW CONCURRENTLY.",
    },
    {
        "id": "TKT-003",
        "account_id": "INITE-9012",
        "region": "ap-southeast-2",
        "date": "2026-07-05",
        "severity": "CRITICAL",
        "topic": "billing_anomaly",
        "summary": "Customer charged $12,400.00 for a $124.00 monthly "
        "subscription. Stripe webhook double-processed the invoice "
        "event (invoice.paid fired twice). Refund initiated via "
        "manual Stripe adjustment. Engineering notified of idempotency gap.",
    },
]

# ── index builder ──────────────────────────────────────────────────────────


def _build_index() -> SimpleKeywordTableIndex:
    """Build and return a ``SimpleKeywordTableIndex`` from the fixture tickets.

    Each ticket is stored as a ``llama-index`` ``Document`` whose text is a
    concatenation of ``topic`` and ``summary`` (the fields most useful for
    keyword matching).  The full ticket metadata is kept in ``Document.metadata``
    so it can be surfaced during retrieval and used for post-filtering.
    """
    docs: list[Document] = []
    for ticket in FIXTURE_TICKETS:
        text = f"{ticket['topic']}: {ticket['summary']}"
        meta = {k: v for k, v in ticket.items() if k != "summary"}
        docs.append(Document(text=text, metadata=meta))

    logger.info("Building keyword index from %d fixture tickets", len(docs))
    index = SimpleKeywordTableIndex.from_documents(docs)
    logger.info("Index built — document store has %d nodes", len(docs))
    return index


# ── retriever class ────────────────────────────────────────────────────────


class EvidenceRetriever:
    """Keyword-based retriever over the synthetic support-ticket corpus.

    Parameters
    ----------
    top_k : int
        Number of top results to return (default 2).
    """

    def __init__(self, top_k: int = 2) -> None:
        self._top_k = top_k
        self._index = _build_index()

    # ── public API ──────────────────────────────────────────────────────

    def retrieve(
        self,
        question: str,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the top-``top_k`` tickets matching *question*.

        Parameters
        ----------
        question : str
            Natural-language question or search phrase.
        filters : dict[str, str] | None
            Optional metadata filters applied as an exact-match post-filter
            (e.g. ``{"region": "us-east-1"}``).  All specified key-value
            pairs must match for a result to be included.

        Returns
        -------
        list[dict[str, Any]]
            Each entry::

                {
                    "id": "TKT-001",
                    "account_id": "ACME-1234",
                    "region": "us-east-1",
                    "date": "2026-07-01",
                    "severity": "HIGH",
                    "topic": "login_failure",
                    "summary": "User unable to log in …",
                    "score": 0.85,          # keyword-match score
                }
        """
        raw = self._index.as_retriever(similarity_top_k=self._top_k).retrieve(
            question
        )

        results: list[dict[str, Any]] = []
        for node in raw:
            ticket: dict[str, Any] = dict(node.metadata)
            ticket["summary"] = node.text.split(": ", 1)[1]
            ticket["score"] = round(node.score, 4) if node.score else 0.0
            results.append(ticket)

        # post-filter on metadata equality
        if filters:
            results = [
                r
                for r in results
                if all(r.get(k) == v for k, v in filters.items())
            ]

        return results[: self._top_k]


# ── convenience singleton ──────────────────────────────────────────────────

_retriever: EvidenceRetriever | None = None


def get_retriever() -> EvidenceRetriever:
    """Return a module-level singleton ``EvidenceRetriever``."""
    global _retriever  # noqa: PLW0603
    if _retriever is None:
        _retriever = EvidenceRetriever()
    return _retriever
