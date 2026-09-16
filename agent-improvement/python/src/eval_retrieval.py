"""Deterministic retrieval probes — no LLM, no retries, no luck.

The end-to-end agent cases let a persistent model brute-force bad ranking
with 15 query rewrites. These probes measure the retrieval build directly:
can the FIRST query surface the official doc?

Run standalone (`uv run python -m src.eval_retrieval`) or as Phase 0 of
`src.eval`. Uses the same `limit` as the `search_docs` tool so the numbers
mean what the agent sees.
"""

from __future__ import annotations

from dataclasses import dataclass

from .retrieval import search as retrieval_search

TOOL_LIMIT = 3

# (natural query, canonical doc that MUST rank)
PROBES: tuple[tuple[str, str], ...] = (
    ("refund policy for annual plans", "consideration-window"),
    ("when does annual subscription renew", "term-anniversary"),
    ("how many named users does Growth include", "named-user-packaging"),
    ("how many named users does Starter include", "named-user-packaging"),
    ("when do added Growth seats appear on invoice", "named-user-packaging"),
    ("business days in processing before support investigates", "orders"),
)


@dataclass
class ProbeOutcome:
    query: str
    expected: str
    passed: bool
    ranked: list[str]


def run_probes() -> list[ProbeOutcome]:
    outcomes: list[ProbeOutcome] = []
    for query, expected in PROBES:
        try:
            ranked = [chunk.doc_id for chunk in retrieval_search(query, limit=TOOL_LIMIT)]
        except Exception as exc:  # noqa: BLE001 — probe reports, never raises
            ranked = [f"ERROR: {exc}"]
        outcomes.append(ProbeOutcome(
            query=query, expected=expected,
            passed=expected in ranked, ranked=ranked,
        ))
    return outcomes


def main() -> int:
    print("Retrieval probes (no LLM, limit=3)\n", flush=True)
    outcomes = run_probes()
    for outcome in outcomes:
        label = "PASS" if outcome.passed else "FAIL"
        print(f"{label}  {outcome.query!r} -> want {outcome.expected}, got {outcome.ranked}", flush=True)
    passed = sum(1 for o in outcomes if o.passed)
    print(f"\n{passed} / {len(outcomes)} retrieval probes passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
