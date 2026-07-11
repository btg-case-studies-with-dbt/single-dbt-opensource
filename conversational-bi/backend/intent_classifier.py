"""Deterministic investigative-intent classifier (Decision 1 = A, TR12.5).

The agentic investigation loop fires ONLY on *investigative* intent — a question
that asks to *explain a movement* in a governed metric ("why did revenue change",
"what drove the token spike"). Plain lookups, group-bys, and argmax/superlative
questions ("which model used the most tokens") keep today's single-shot path
byte-for-byte and return ``investigation.status:"not_investigated"``.

This is a **pure, deterministic regex** — no LLM, no network — so the trigger is
cheap, testable, and can never itself hallucinate an investigation. The safe
default on any uncertainty is ``lookup`` (return ``False``): a misclassified
investigative question merely loses the extra evidence; a misclassified lookup
would spend latency and risk a fabricated story, so we bias hard toward lookup.

Contract (verified against ``eval/intent_classifier_fixtures.csv``, all 20 rows):

* Investigative triggers are *explanatory verbs/phrases about a change*:
  ``why`` · ``drove/driving/driven`` · ``caused/cause of`` · ``what's behind`` ·
  ``explain`` · ``accounts for`` · ``reason for`` · ``break down`` **paired with**
  a movement noun (change/shift/drop/movement/…).
* Superlative/argmax frames ("which model used the **most** tokens") are NOT
  investigative — they are governed lookups handled by ``check_rank_coverage``.
* Comparison metrics ("revenue **growth rate** compared to last quarter") are NOT
  investigative — "growth"/"compared" alone never trigger the loop.
"""

from __future__ import annotations

import re

# ── movement nouns (a metric *changed*) ──────────────────────────────────────
# Used both as a companion for the weak "break down" trigger and as documentation
# of what "a movement" means. Kept as a word-boundary alternation.
_MOVEMENT_NOUNS = (
    "change",
    "changed",
    "movement",
    "shift",
    "drop",
    "decline",
    "increase",
    "spike",
    "fall",
    "rise",
    "growth",
    "swing",
    "jump",
)
_MOVEMENT_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in _MOVEMENT_NOUNS) + r")\b",
    re.IGNORECASE,
)

# ── STRONG explanatory triggers (match alone → investigative) ────────────────
# Each is an unambiguous request to EXPLAIN, not merely to retrieve. Word
# boundaries keep "why" from firing on "always" and "cause" from "because" noise.
# None of these tokens appear in any lookup fixture row.
_STRONG_PATTERNS = [
    r"\bwhy\b",                       # "Why did net revenue change…"
    r"\bdrove\b",                     # "What drove the change…"
    r"\bdriving\b",                   # "What is driving the decline…"
    r"\bdriven\s+by\b",              # "…driven by…"
    r"\bcaused?\b",                   # "What caused revenue to fall…" / "cause"
    r"\bbehind\b",                    # "What's behind the shift…"
    r"\bexplain\b",                   # "Explain the drop…"
    r"\baccounts?\s+for\b",          # "What accounts for the increase…"
    r"\breason\s+for\b",             # "Reason for the spike…"
]
_STRONG_RE = re.compile("|".join(_STRONG_PATTERNS), re.IGNORECASE)

# ── WEAK trigger: "break down" is investigative ONLY with a movement noun ─────
# "Break down net revenue by segment" is a group-by lookup; "Break down the
# MOVEMENT in gross revenue" is investigative. The movement noun is the
# discriminator, so this trigger requires both.
_BREAKDOWN_RE = re.compile(r"\bbreak\s*down\b", re.IGNORECASE)


def is_investigative(question: str | None) -> bool:
    """Return ``True`` iff the question asks to *explain a metric movement*.

    Pure and deterministic. Safe default is ``False`` (lookup) on any empty or
    unrecognised input — we never spend an investigation we are unsure is
    warranted.

    Parameters
    ----------
    question
        The raw (already PII-redacted) natural-language question.

    Returns
    -------
    bool
        ``True`` → run the bounded investigation loop (if the base answer is
        ``answered``); ``False`` → keep the single-shot lookup path.
    """
    if not question or not question.strip():
        return False

    q = question.strip()

    # Strong explanatory trigger → investigative.
    if _STRONG_RE.search(q):
        return True

    # Weak trigger: "break down" only counts when a movement noun is present.
    if _BREAKDOWN_RE.search(q) and _MOVEMENT_RE.search(q):
        return True

    # Everything else — plain totals, group-bys, argmax, comparison metrics — is
    # a lookup. Bias to lookup on uncertainty.
    return False
