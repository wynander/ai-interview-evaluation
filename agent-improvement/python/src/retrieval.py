"""Retrieval layer — THIS IS YOUR MAIN 0-1 BUILD.

The starter `search()` below is intentionally naive: full table scan,
token overlap in Python, no chunking, no index, returns huge bodies.
At ~3000+ docs it is slow and easily fooled by distractor drafts.

Candidate: rebuild this. Suggested shape (you decide the details):

  1. Ingestion: chunk long bodies, extract/normalize metadata
     (status/trust/effective_from/audience), build tsvector or embeddings.
     Put migrations in db/migrations/.
  2. Search: filter (status=current, trust=official, audience=customer_facing
     for user answers) THEN rank (FTS + recency, or hybrid + rerank).
  3. Output: top-k chunks with doc_id + title + chunk span + score, small
     enough to fit context. Never return internal docs to the model for
     customer answers — or mark them clearly so guardrails can block them.
  4. Citations: return doc_ids so tools.py can cite them and evals can check
     grounding.

You may add dependencies (e.g. sentence-transformers, pgvector) but the
default Postgres FTS path should be enough to pass if done well.
Document tradeoffs in DESIGN.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import db


@dataclass
class Chunk:
    doc_id: str
    title: str
    body: str
    status: str
    trust: str
    effective_from: str
    audience: str
    score: float = 0.0


def chunk_text(body: str, max_chars: int = 1200) -> list[str]:
    """TODO (candidate): implement real chunking (paragraph/sentence-aware, overlap).

    Starter just slices naively. Long docs will truncate mid-sentence.
    """
    return [body[i : i + max_chars] for i in range(0, len(body), max_chars)] or [""]


def search(query: str, limit: int = 5) -> list[Chunk]:
    """TODO (candidate): replace this naive scan with indexed retrieval.

    Current flaws (all intentional):
      - SELECTs every document and scores in Python (full scan, slow at scale).
      - No metadata filtering: draft/untrusted/archived rank alongside official.
      - No audience check: internal docs leak into customer answers.
      - Returns full bodies: blows up context, no chunk spans.
    """
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not terms:
        return []

    # BAD (intentional): full scan + Python scoring. Slow at 3000+ docs.
    rows = db.fetch_all("SELECT doc_id, title, body, status, trust, effective_from, audience FROM documents")

    scored: list[tuple[int, dict]] = []
    for row in rows:
        doc_terms = set(re.findall(r"[a-z0-9]+", f"{row['title']} {row['body']}".lower()))
        score = len(terms & doc_terms)
        if score:
            scored.append((score, row))

    scored.sort(key=lambda item: (-item[0], item[1]["doc_id"]))
    chunks: list[Chunk] = []
    for score, row in scored[:limit]:
        # Naive: first chunk only, full body if short.
        first = chunk_text(row["body"])[0]
        chunks.append(Chunk(
            doc_id=row["doc_id"],
            title=row["title"],
            body=first,
            status=row["status"],
            trust=row["trust"],
            effective_from=row["effective_from"],
            audience=row["audience"],
            score=float(score),
        ))
    return chunks


def get_document(doc_id: str) -> Chunk | None:
    """Fetch one doc by ID (latest version). Used for citation drill-down."""
    row = db.fetch_one(
        "SELECT doc_id, title, body, status, trust, effective_from, audience"
        " FROM documents WHERE doc_id = %s ORDER BY version DESC LIMIT 1",
        (doc_id,),
    )
    if not row:
        return None
    return Chunk(
        doc_id=row["doc_id"], title=row["title"], body=row["body"],
        status=row["status"], trust=row["trust"],
        effective_from=row["effective_from"], audience=row["audience"],
    )
