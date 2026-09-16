/**
 * Deterministic retrieval probes — no LLM, no retries, no luck.
 *
 * The end-to-end agent cases let a persistent model brute-force bad ranking
 * with 15 query rewrites. These probes measure the retrieval build directly:
 * can the FIRST query surface the official doc?
 *
 * Run standalone (`npx tsx src/eval-retrieval.ts`) or as Phase 0 of
 * `src/eval.ts`. Uses the same `limit` as the `search_docs` tool so the numbers
 * mean what the agent sees.
 */
import { search as retrievalSearch } from "./retrieval";
import { runIfMain } from "./runtime-helpers";

export const TOOL_LIMIT = 3;

// (natural query, canonical doc that MUST rank)
export const PROBES: Array<[string, string]> = [
  ["refund policy for annual plans", "consideration-window"],
  ["when does annual subscription renew", "term-anniversary"],
  ["how many named users does Growth include", "named-user-packaging"],
  ["how many named users does Starter include", "named-user-packaging"],
  ["when do added Growth seats appear on invoice", "named-user-packaging"],
  ["business days in processing before support investigates", "orders"],
];

export interface ProbeOutcome {
  query: string;
  expected: string;
  passed: boolean;
  ranked: string[];
}

export async function runProbes(): Promise<ProbeOutcome[]> {
  const outcomes: ProbeOutcome[] = [];
  for (const [query, expected] of PROBES) {
    let ranked: string[];
    try {
      ranked = (await retrievalSearch(query, TOOL_LIMIT)).map((chunk) => chunk.doc_id);
    } catch (error) {
      ranked = [`ERROR: ${error instanceof Error ? error.message : String(error)}`];
    }
    outcomes.push({ query, expected, passed: ranked.includes(expected), ranked });
  }
  return outcomes;
}

async function main(): Promise<number> {
  console.log("Retrieval probes (no LLM, limit=3)\n");
  const outcomes = await runProbes();
  for (const outcome of outcomes) {
    const label = outcome.passed ? "PASS" : "FAIL";
    console.log(`${label}  ${JSON.stringify(outcome.query)} -> want ${outcome.expected}, got [${outcome.ranked.join(", ")}]`);
  }
  const passed = outcomes.filter((o) => o.passed).length;
  console.log(`\n${passed} / ${outcomes.length} retrieval probes passed`);
  return 0;
}

runIfMain("src/eval-retrieval.ts", main);
