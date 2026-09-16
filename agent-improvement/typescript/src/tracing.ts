/**
 * Minimal JSONL tracing + token/cost counters.
 *
 * Starter only logs tool calls. Candidate TODO:
 *  - Log model calls (tokens in/out, latency, est. cost) from src/agent.ts.
 *  - Add a `traces/summary.ts` or note in DESIGN.md: avg tool calls / case,
 *    avg latency, est. cost per 100 eval runs.
 *  - Redact secrets (API keys, emails?) before writing. Eval checks that
 *    OPENAI_API_KEY never appears in traces/.
 *
 * Keep it dependency-free and human-readable (one JSON object per line).
 */
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const TRACES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "traces");

function redact(text: string): string {
  const secret = process.env.OPENAI_API_KEY ?? "";
  if (secret && text.includes(secret)) {
    text = text.split(secret).join("[REDACTED]");
  }
  return text;
}

export function logEvent(event: Record<string, unknown>): void {
  mkdirSync(TRACES_DIR, { recursive: true });
  const entry = { ts: Date.now() / 1000, ...event };
  const line = redact(JSON.stringify(entry));
  // One file per day; simple and greppable. Node's single-threaded event
  // loop + sync append keeps eval-time concurrent writes from interleaving.
  const day = new Date().toISOString().slice(0, 10);
  appendFileSync(join(TRACES_DIR, `${day}.jsonl`), line + "\n", "utf-8");
}

export function logToolCall(
  name: string,
  args: Record<string, unknown>,
  latencyMs: number,
  ok: boolean,
  summary = "",
): void {
  logEvent({
    type: "tool_call",
    tool: name,
    arguments: args,
    latency_ms: Math.round(latencyMs * 10) / 10,
    ok,
    result_summary: summary.slice(0, 500),
  });
}

/** Return trace files containing the raw API key (should be empty). */
export function checkNoSecrets(): string[] {
  const secret = process.env.OPENAI_API_KEY ?? "";
  if (!secret || !existsSync(TRACES_DIR)) return [];
  const leaked: string[] = [];
  for (const file of readdirSync(TRACES_DIR)) {
    if (!file.endsWith(".jsonl")) continue;
    const content = readFileSync(join(TRACES_DIR, file), "utf-8");
    if (content.includes(secret)) leaked.push(file);
  }
  return leaked;
}
