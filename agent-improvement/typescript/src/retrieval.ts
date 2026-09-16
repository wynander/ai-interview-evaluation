/**
 * Retrieval layer — THIS IS YOUR MAIN 0-1 BUILD.
 *
 * The starter `search()` below is intentionally naive: full table scan,
 * token overlap in JS, no chunking, no index, returns huge bodies.
 * At ~3000+ docs it is slow and easily fooled by distractor drafts.
 *
 * Candidate: rebuild this. What matters: official, current docs rank first;
 * results are small enough to fit context; every result carries its doc_id
 * so answers can cite grounding. Put migrations in src/db/migrations/ and
 * keep src/db/schema.ts in sync. Document tradeoffs in DESIGN.md.
 */
import { desc, eq } from "drizzle-orm";

import { db } from "./db";
import { documents } from "./db/schema";

export interface Chunk {
  doc_id: string;
  title: string;
  body: string;
  status: string;
  trust: string;
  effective_from: string;
  audience: string;
  score?: number;
}

type DocRow = typeof documents.$inferSelect;

/**
 * TODO (candidate): split long bodies so results fit context.
 * Starter just slices naively. Long docs will truncate mid-sentence.
 */
export function chunkText(body: string, maxChars = 1200): string[] {
  const out: string[] = [];
  for (let i = 0; i < body.length; i += maxChars) out.push(body.slice(i, i + maxChars));
  return out.length > 0 ? out : [""];
}

/**
 * TODO (candidate): replace this naive scan.
 *
 * Current flaws (all intentional):
 *  - SELECTs every document and scores in JS (full scan, slow at scale).
 *  - No metadata filtering: draft/untrusted/archived rank alongside official.
 *  - No audience check: internal docs leak into customer answers.
 *  - Returns full bodies: blows up context, no chunk spans.
 */
export async function search(query: string, limit = 5): Promise<Chunk[]> {
  const terms = new Set((query.toLowerCase().match(/[a-z0-9]+/g) ?? []));
  if (terms.size === 0) return [];

  // BAD (intentional): full scan + JS scoring. Slow at 3000+ docs.
  const rows = await db().select().from(documents);

  const scored: Array<{ score: number; row: DocRow }> = [];
  for (const row of rows) {
    const docTerms = new Set(`${row.title} ${row.body}`.toLowerCase().match(/[a-z0-9]+/g) ?? []);
    let score = 0;
    for (const term of terms) if (docTerms.has(term)) score++;
    if (score > 0) scored.push({ score, row });
  }

  scored.sort((a, b) => b.score - a.score || (a.row.docId < b.row.docId ? -1 : 1));
  const chunks: Chunk[] = [];
  for (const { score, row } of scored.slice(0, limit)) {
    // Naive: first chunk only, full body if short.
    const first = chunkText(row.body)[0];
    chunks.push({
      doc_id: row.docId,
      title: row.title,
      body: first,
      status: row.status,
      trust: row.trust,
      effective_from: row.effectiveFrom,
      audience: row.audience,
      score,
    });
  }
  return chunks;
}

/** Fetch one doc by ID (latest version). Used for citation drill-down. */
export async function getDocument(docId: string): Promise<Chunk | null> {
  const rows = await db()
    .select()
    .from(documents)
    .where(eq(documents.docId, docId))
    .orderBy(desc(documents.version))
    .limit(1);
  const row = rows[0];
  if (!row) return null;
  return {
    doc_id: row.docId,
    title: row.title,
    body: row.body,
    status: row.status,
    trust: row.trust,
    effective_from: row.effectiveFrom,
    audience: row.audience,
  };
}
