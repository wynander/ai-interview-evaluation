/**
 * Model-backed evaluations for take-home v2.
 *
 * 31 LLM cases across 10 categories + 6 retrieval probes + static checks.
 * Custom: evals/custom-cases.ts (candidate's own 5+) auto-appended.
 * Set CHAOS=1 to run the same suite against flaky services (see eval-chaos).
 *
 * Design notes:
 *  - Deterministic fact checks gate pass/fail (stable). LLM judge scores
 *    quality alongside but never fails (see evals/judge.ts).
 *  - Red-team cases assert DB invariants: row counts unchanged, hostile
 *    statements rejected at parse/plan stage (never executed).
 *  - Two-phase execution: pure cases run concurrently (6 workers), then
 *    ticket-delta / DB-invariant cases run sequentially in order. Use --cases
 *    to iterate on a subset.
 *  - Static checks (no LLM): .dockerignore leak, trace secret scan,
 *    retrieval latency probe, audit-log presence.
 */
import "dotenv/config";

import { execFile } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { promisify } from "node:util";

import { AgentConfigurationError, AgentSession, type AgentResult } from "./agent";
import { fetchAll, fetchOne } from "./db";
import { resetTickets, runIfMain, tableCounts, ticketCount } from "./runtime-helpers";
import { runProbes, type ProbeOutcome } from "./eval-retrieval";

const execFileAsync = promisify(execFile);

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
import { CASES, DEFAULT_MAX_TOOL_CALLS, REDTEAM_CANARY_VALUE, type EvalCase } from "./eval-cases";
export const CASE_TIMEOUT_SECONDS = 120;
export interface EvalOutcome {
  case: EvalCase;
  passed: boolean;
  reason: string;
  result: AgentResult;
  turnResults: AgentResult[];
  judgeScore: number | null;
  judgeRationale: string;
}

export const HTML_REPORT_PATH = join(ROOT, "eval-baseline.html");


function containsFact(haystack: string, fact: string): boolean {
  return haystack.toLowerCase().includes(fact.toLowerCase());
}

function parseToolResult(raw: string | null): unknown {
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

async function checkCase(
  case_: EvalCase,
  result: AgentResult,
  ticketDelta: number,
  invariantBefore: Record<string, number> | null,
): Promise<string | null> {
  if (result.error) return result.error;

  const toolNames = new Set(result.toolCalls.map((c) => c.name));
  const missing = (case_.requiredTools ?? []).filter((name) => !toolNames.has(name));
  if (missing.length > 0) return `missing required evidence tool(s): ${missing.join(", ")}`;

  const trace = result.toolCalls.map((c) => `${c.name} ${JSON.stringify(c.arguments)} ${c.result ?? ""}`).join("\n");
  for (const group of case_.traceFactGroups ?? []) {
    if (!group.some((fact) => containsFact(trace, fact))) {
      return `trace missing one of: ${group.join(", ")}`;
    }
  }

  if (case_.requireCitation?.length) {
    const traceLower = trace.toLowerCase();
    if (!case_.requireCitation.some((docId) => traceLower.includes(docId.toLowerCase()))) {
      return `trace missing citation of one of: ${case_.requireCitation.join(", ")}`;
    }
  }

  const response = result.response;
  for (const group of case_.responseFactGroups ?? []) {
    if (!group.some((fact) => containsFact(response, fact))) {
      return `response missing one of: ${group.join(", ")}`;
    }
  }

  if (case_.dynamicFacts) {
    for (const group of await case_.dynamicFacts()) {
      if (!group.some((fact) => containsFact(response, fact))) {
        return `response missing one of (dynamic): ${group.join(", ")}`;
      }
    }
  }

  for (const forbidden of case_.forbidInResponse ?? []) {
    if (response.toLowerCase().includes(forbidden.toLowerCase())) {
      return `response contains forbidden text: ${JSON.stringify(forbidden)}`;
    }
  }

  if (case_.expectedTicketDelta !== undefined && case_.expectedTicketDelta !== null && ticketDelta !== case_.expectedTicketDelta) {
    return `expected ticket count change ${case_.expectedTicketDelta}, got ${ticketDelta}`;
  }

  if (case_.requireRelatedOrderId) {
    let linked = false;
    for (const call of result.toolCalls) {
      if (call.name !== "create_support_ticket" || !call.result) continue;
      const parsed = parseToolResult(call.result) as Record<string, unknown> | null;
      if (parsed && typeof parsed === "object" && parsed.related_order_id === case_.requireRelatedOrderId) {
        linked = true;
        break;
      }
    }
    if (!linked) return `created ticket missing related_order_id ${case_.requireRelatedOrderId}`;
  }

  if (case_.dbInvariantTables && invariantBefore) {
    const after = await tableCounts();
    for (const table of case_.dbInvariantTables) {
      if (after[table] !== invariantBefore[table]) {
        return `DB invariant violated: ${table} changed ${invariantBefore[table]} -> ${after[table]}`;
      }
    }
  }

  return null;
}

function combineTurnResults(turnResults: AgentResult[]): AgentResult {
  if (turnResults.length === 0) {
    return { response: "", toolCalls: [], error: null, latencyMs: 0 };
  }
  const last = turnResults[turnResults.length - 1];
  return {
    response: last.response,
    toolCalls: turnResults.flatMap((r) => r.toolCalls),
    error: last.error,
    latencyMs: turnResults.reduce((sum, r) => sum + r.latencyMs, 0),
  };
}

/** Judge categories (non-gating quality signal). */
const JUDGE_CATEGORIES = new Set(["retrieval", "multi-turn", "tools", "guardrail"]);

interface JudgeModule {
  score: (response: string, expected: string, trace: string) => { score: number; rationale: string };
}

let judgeModule: JudgeModule | null = null;

async function runJudge(response: string, expected: string, trace: string): Promise<{ score: number; rationale: string }> {
  if (!judgeModule) {
    judgeModule = (await import("../evals/judge")) as unknown as JudgeModule;
  }
  const loaded: JudgeModule = judgeModule;
  return loaded.score(response, expected, trace);
}

interface CaseProgress {
  turnResults: AgentResult[];
  ticketDelta: number;
}

async function executeCase(case_: EvalCase, progress: CaseProgress): Promise<EvalOutcome> {
  // Only isolated cases need a clean ticket slate; parallel cases must not
  // wipe state out from under each other (their strays are wiped by the
  // next isolated reset, and nothing in the parallel batch counts tickets).
  if (needsIsolation(case_)) {
    await resetTickets();
  }
  const invariantBefore = case_.dbInvariantTables ? await tableCounts() : null;
  const initialTicketCount = await ticketCount();
  const session = new AgentSession();
  const budget = case_.maxToolCalls ?? DEFAULT_MAX_TOOL_CALLS;
  for (const turn of case_.turns) {
    const turnResult = await session.run(turn);
    progress.turnResults.push(turnResult);
    if (turnResult.error) break;
    const totalCalls = progress.turnResults.reduce((sum, r) => sum + r.toolCalls.length, 0);
    if (totalCalls > budget) {
      progress.ticketDelta = (await ticketCount()) - initialTicketCount;
      const combined = combineTurnResults(progress.turnResults);
      const reason = `exceeded case budget of ${budget} tool calls (${totalCalls} used) — retrieve more efficiently`;
      console.log(`FAIL  ${case_.name} (${reason})`);
      return { case: case_, passed: false, reason, result: combined, turnResults: [...progress.turnResults], judgeScore: null, judgeRationale: "" };
    }
  }

  progress.ticketDelta = (await ticketCount()) - initialTicketCount;
  const combined = combineTurnResults(progress.turnResults);
  const reason = await checkCase(case_, combined, progress.ticketDelta, invariantBefore);
  return {
    case: case_,
    passed: reason === null,
    reason: reason ?? "all positive checks passed",
    result: combined,
    turnResults: [...progress.turnResults],
    judgeScore: null,
    judgeRationale: "",
  };
}

const CASE_TIMINGS: Record<string, number> = {};

async function runCase(case_: EvalCase, noJudge: boolean): Promise<EvalOutcome> {
  console.log(`RUN   [${case_.category ?? "general"}] ${case_.name}`);
  const started = Date.now();
  const progress: CaseProgress = { turnResults: [], ticketDelta: 0 };
  let settled = false;

  const work = (async (): Promise<EvalOutcome> => {
    const outcome = await executeCase(case_, progress);
    if (!noJudge && JUDGE_CATEGORIES.has(case_.category ?? "")) {
      try {
        const trace = outcome.result.toolCalls.map((c) => `${c.name} ${c.result ?? ""}`).join("\n");
        const { score, rationale } = await runJudge(outcome.result.response, case_.expectedAnswer, trace);
        outcome.judgeScore = score;
        outcome.judgeRationale = rationale;
      } catch (error) {
        outcome.judgeRationale = `judge error: ${error instanceof Error ? error.message : String(error)}`;
      }
    }
    return outcome;
  })();

  const timeoutMs = CASE_TIMEOUT_SECONDS * 1000 * case_.turns.length;
  const timeout = new Promise<EvalOutcome>((resolve) => {
    setTimeout(() => {
      if (settled) return;
      settled = true;
      const completed = progress.turnResults.length;
      const reason = `timed out after ${CASE_TIMEOUT_SECONDS * case_.turns.length}s (${completed}/${case_.turns.length} turns)`;
      const combined = combineTurnResults(progress.turnResults);
      console.log(`FAIL  ${case_.name}`);
      resolve({
        case: case_,
        passed: false,
        reason,
        result: { response: combined.response, toolCalls: combined.toolCalls, error: reason, latencyMs: combined.latencyMs },
        turnResults: [...progress.turnResults],
        judgeScore: null,
        judgeRationale: "",
      });
    }, timeoutMs);
  });

  const outcome = await Promise.race([
    work.then((o) => {
      settled = true;
      return o;
    }),
    timeout,
  ]);
  // A timed-out case's background work may still finish later; its prints are
  // harmless (the outcome above is what counts).

  const label = outcome.passed ? "PASS" : "FAIL";
  const judgeBit = outcome.judgeScore !== null ? ` judge=${outcome.judgeScore.toFixed(2)}` : "";
  const elapsed = (Date.now() - started) / 1000;
  CASE_TIMINGS[case_.name] = elapsed;
  const calls = outcome.turnResults.reduce((sum, r) => sum + r.toolCalls.length, 0);
  console.log(`${label}  ${case_.name}${judgeBit} (${elapsed.toFixed(0)}s, ${calls} calls)`);
  return outcome;
}

export function needsIsolation(case_: EvalCase): boolean {
  // Ticket deltas and DB invariants race under concurrency, so cases that
  // measure them run sequentially. Auto-derived so candidate custom cases
  // with delta/invariant checks are isolated too.
  return Boolean(
    (case_.isolated ?? false) ||
      (case_.expectedTicketDelta !== undefined && case_.expectedTicketDelta !== null) ||
      (case_.dbInvariantTables !== undefined && case_.dbInvariantTables !== null),
  );
}

export async function runEvaluation(cases: EvalCase[], workers = 6, noJudge = false): Promise<EvalOutcome[]> {
  if (cases.length === 0) return [];
  const parallel = cases.filter((c) => !needsIsolation(c));
  const isolated = cases.filter((c) => needsIsolation(c));
  const outcomes: EvalOutcome[] = [];
  if (parallel.length > 0) {
    console.log(`Phase 1: ${parallel.length} parallel cases (${workers} workers)\n`);
    // Bounded worker pool over the parallel batch.
    let next = 0;
    const runNext = async (): Promise<void> => {
      while (next < parallel.length) {
        const index = next++;
        outcomes.push(await runCase(parallel[index], noJudge));
      }
    };
    await Promise.all(Array.from({ length: Math.min(workers, parallel.length) }, () => runNext()));
  }
  if (isolated.length > 0) {
    console.log(`\nPhase 2: ${isolated.length} isolated cases (sequential)\n`);
    for (const case_ of isolated) {
      outcomes.push(await runCase(case_, noJudge));
    }
  }
  // Restore declared order for the report.
  const byName = new Map(outcomes.map((o) => [o.case.name, o]));
  return cases.map((c) => byName.get(c.name)!);
}

export async function loadCustomCases(): Promise<EvalCase[]> {
  const customPath = join(ROOT, "evals", "custom-cases.ts");
  if (!existsSync(customPath)) return [];
  const module = (await import(pathToFileURL(customPath).href)) as { CUSTOM_CASES?: EvalCase[] };
  const custom = module.CUSTOM_CASES ?? [];
  for (const case_ of custom) case_.category = "custom";
  return custom;
}

// --- static checks (no LLM) ---

export interface StaticResult {
  name: string;
  passed: boolean;
  detail: string;
}

export async function staticChecks(): Promise<StaticResult[]> {
  const results: StaticResult[] = [];

  const dockerignore = join(ROOT, ".dockerignore");
  const dockerignoreBlocksEnv = (): boolean => {
    if (!existsSync(dockerignore)) return false;
    for (const line of readFileSync(dockerignore, "utf-8").split("\n")) {
      const entry = line.split("#", 1)[0].trim();
      if ([".env", ".env*", "*.env"].includes(entry) || (entry.startsWith(".env") && entry !== ".venv/")) {
        return true;
      }
    }
    return false;
  };

  if (dockerignoreBlocksEnv()) {
    results.push({ name: "dockerignore blocks .env", passed: true, detail: "ok" });
  } else {
    results.push({ name: "dockerignore blocks .env", passed: false, detail: ".dockerignore must exclude .env (secret leak)" });
  }

  const dockerfile = join(ROOT, "Dockerfile");
  if (existsSync(dockerfile) && readFileSync(dockerfile, "utf-8").includes("COPY . .") && !dockerignoreBlocksEnv()) {
    results.push({
      name: "dockerfile secret hygiene",
      passed: false,
      detail: "COPY . . with no .dockerignore exclusion bakes .env into the image",
    });
  } else {
    results.push({ name: "dockerfile secret hygiene", passed: true, detail: "ok" });
  }

  try {
    const { checkNoSecrets } = await import("./tracing");
    const leaked = checkNoSecrets() as string[];
    results.push({
      name: "traces contain no API key",
      passed: leaked.length === 0,
      detail: leaked.length === 0 ? "ok" : `key found in: ${leaked.join(", ")}`,
    });
  } catch (error) {
    results.push({ name: "traces contain no API key", passed: false, detail: String(error) });
  }

  let dbUp = true;
  let dbError = "";
  try {
    const { ping } = await import("./db");
    await ping();
  } catch (error) {
    dbUp = false;
    dbError = `db unreachable (${error instanceof Error ? error.message : String(error)}). Is \`docker compose up -d\` running?`;
  }

  if (!dbUp) {
    results.push({ name: "retrieval latency probe", passed: false, detail: dbError });
    results.push({ name: "audit log written", passed: false, detail: dbError });
    return results;
  }

  try {
    const { search: retrievalSearch } = await import("./retrieval");
    const latencies: number[] = [];
    for (let i = 0; i < 3; i++) {
      const started = Date.now();
      await retrievalSearch("refund policy annual plans", 5);
      latencies.push(Date.now() - started);
    }
    const p50 = latencies.sort((a, b) => a - b)[1];
    const ok = p50 < 10_000;
    results.push({
      name: "retrieval latency probe",
      passed: ok,
      detail: `p50 ${Math.round(p50)}ms over 3 probes (warn >2000ms, fail >10000ms)`,
    });
  } catch (error) {
    results.push({ name: "retrieval latency probe", passed: false, detail: `search failed: ${String(error)}` });
  }

  try {
    const row = await fetchOne<{ n: string }>("SELECT count(*) AS n FROM tool_audit_log");
    const n = row ? Number(row.n) : 0;
    results.push({ name: "audit log written", passed: n > 0, detail: `${n} rows in tool_audit_log (run eval-dev first)` });
  } catch (error) {
    results.push({ name: "audit log written", passed: false, detail: String(error) });
  }

  try {
    const rows = await fetchAll(
      "SELECT indexname FROM pg_indexes " +
        "WHERE schemaname = 'public' AND tablename = 'tickets' " +
        "AND indexdef ILIKE '%%UNIQUE%%' AND indexname <> 'tickets_pkey'",
    );
    results.push({
      name: "tickets dedup constraint",
      passed: rows.length > 0,
      detail:
        rows.length > 0
          ? `${rows.length} extra unique index(es) on tickets`
          : "no dedup unique index on tickets (add a migration)",
    });
  } catch (error) {
    results.push({ name: "tickets dedup constraint", passed: false, detail: String(error) });
  }

  // Services-API integration checks. ORDER MATTERS: the authed error-shape
  // probes below must run BEFORE the log-leak grep, so a logging server has
  // fresh key-bearing lines to be caught by (fresh containers start empty).
  const servicesUrl = process.env.SERVICES_API_URL ?? "http://localhost:8001";
  const servicesKey = process.env.SERVICES_API_KEY ?? "dev-insecure-key";

  try {
    const response = await fetch(`${servicesUrl}/api/customers/C123`, { signal: AbortSignal.timeout(5000) });
    if (response.status === 401) {
      results.push({ name: "services auth requires key", passed: true, detail: "ok" });
    } else {
      results.push({
        name: "services auth requires key",
        passed: false,
        detail: `missing key returned ${response.status}, want 401`,
      });
    }
  } catch (error) {
    results.push({
      name: "services auth requires key",
      passed: false,
      detail: `services unreachable (${error instanceof Error ? error.message : String(error)}). Is \`docker compose up -d\` running?`,
    });
  }

  try {
    const shapes: string[] = [];
    for (let i = 0; i < 5; i++) {
      const response = await fetch(`${servicesUrl}/api/customers/C000-NOPE`, {
        headers: { "X-API-Key": servicesKey },
        signal: AbortSignal.timeout(5000),
      });
      const contentType = response.headers.get("content-type") ?? "";
      shapes.push(`${response.status}:${contentType.includes("application/json") ? "json" : "text"}`);
    }
    if (shapes.every((s) => s === "404:json")) {
      results.push({ name: "services errors are JSON 404s", passed: true, detail: "ok" });
    } else {
      results.push({
        name: "services errors are JSON 404s",
        passed: false,
        detail: `got [${shapes.join(", ")}], want 5x 404:json`,
      });
    }
  } catch (error) {
    results.push({ name: "services errors are JSON 404s", passed: false, detail: `services unreachable (${String(error)})` });
  }

  try {
    const sandboxSrc = readFileSync(join(ROOT, "src", "sandbox.ts"), "utf-8");
    // A real call in code — not a comment/docstring mention (the starter
    // docstring names agentDatabaseUrl without using it).
    const usesReadonly = sandboxSrc.split("\n").some((line) => {
      const trimmed = line.trim();
      if (trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*")) return false;
      return /agentDatabaseUrl\(\)/.test(line);
    });
    results.push({
      name: "run_sql uses readonly role",
      passed: usesReadonly,
      detail: usesReadonly ? "ok" : "run_sql still connects as superuser (see sandbox.ts TODO)",
    });
  } catch (error) {
    results.push({ name: "run_sql uses readonly role", passed: false, detail: String(error) });
  }

  try {
    const { stdout, stderr } = await execFileAsync("docker", ["compose", "logs", "--no-log-prefix", "--tail", "500", "web"], {
      cwd: ROOT,
      timeout: 20_000,
    });
    const logs = `${stdout}${stderr}`.toLowerCase();
    if (logs.includes("x-api-key")) {
      results.push({
        name: "services logs contain no API keys",
        passed: false,
        detail: "request headers (with keys) found in web service logs",
      });
    } else {
      results.push({ name: "services logs contain no API keys", passed: true, detail: "ok" });
    }
  } catch (error) {
    results.push({ name: "services logs contain no API keys", passed: false, detail: `could not read logs (${String(error)})` });
  }

  return results;
}

export interface ReportPayload {
  passed: number;
  total: number;
  cases: Array<Record<string, unknown>>;
  probes?: Array<Record<string, unknown>>;
  statics?: Array<Record<string, unknown>>;
}

export function outcomesToReport(
  outcomes: EvalOutcome[],
  probes: ProbeOutcome[] | null = null,
  statics: StaticResult[] | null = null,
): ReportPayload {
  const cases = outcomes.map((outcome) => ({
    name: outcome.case.name,
    category: outcome.case.category ?? "general",
    passed: outcome.passed,
    reason: outcome.reason,
    expected_answer: outcome.case.expectedAnswer,
    expected_why: outcome.case.expectedWhy,
    judge_score: outcome.judgeScore,
    judge_rationale: outcome.judgeRationale,
    turns: outcome.turnResults.map((turnResult, index) => ({
      input: outcome.case.turns[index] ?? "",
      response: turnResult.response,
      error: turnResult.error,
      tool_calls: turnResult.toolCalls.map((call) => ({
        name: call.name,
        arguments: call.arguments,
        result: parseToolResult(call.result),
      })),
    })),
  }));
  const passed = outcomes.filter((o) => o.passed).length;
  const report: ReportPayload = { passed, total: outcomes.length, cases };
  // Additive keys — the report renderer ignores unknown top-level keys.
  if (probes !== null) {
    report.probes = probes.map((p) => ({ query: p.query, expected: p.expected, passed: p.passed, ranked: p.ranked }));
  }
  if (statics !== null) {
    report.statics = statics.map(({ name, passed: ok, detail }) => ({ name, passed: ok, detail }));
  }
  return report;
}

export function writeHtmlReport(
  outcomes: EvalOutcome[],
  probes: ProbeOutcome[] | null = null,
  statics: StaticResult[] | null = null,
): void {
  const payload = JSON.stringify(outcomesToReport(outcomes, probes, statics), null, 2).replace(/</g, "\\u003c");
  const html = readFileSync(HTML_REPORT_PATH, "utf-8");
  const start = '<script type="application/json" id="eval-data">';
  const end = "</script>";
  const startAt = html.indexOf(start);
  const endAt = startAt === -1 ? -1 : html.indexOf(end, startAt);
  if (startAt === -1 || endAt === -1) {
    throw new Error(`${HTML_REPORT_PATH} is missing the eval-data script tag`);
  }
  writeFileSync(HTML_REPORT_PATH, html.slice(0, startAt + start.length) + "\n" + payload + "\n    " + html.slice(endAt), "utf-8");
}

function printVerbose(outcome: EvalOutcome): void {
  outcome.turnResults.forEach((turnResult, index) => {
    console.log(`  turn ${index + 1}: ${outcome.case.turns[index]}`);
    console.log(`  response: ${turnResult.response}`);
    if (turnResult.error) console.log(`  error: ${turnResult.error}`);
    for (const call of turnResult.toolCalls) {
      console.log(`  tool: ${call.name}(${JSON.stringify(call.arguments)})`);
      if (call.result !== null) console.log(`  result: ${call.result.slice(0, 1500)}`);
    }
  });
  if (!outcome.passed) console.log(`  reason: ${outcome.reason}`);
  if (outcome.judgeScore !== null) console.log(`  judge: ${outcome.judgeScore.toFixed(2)} — ${outcome.judgeRationale}`);
}

interface CliArgs {
  verbose: boolean;
  cases: string;
  workers: number;
  noJudge: boolean;
  staticOnly: boolean;
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = { verbose: false, cases: "", workers: 6, noJudge: false, staticOnly: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--verbose") args.verbose = true;
    else if (argv[i] === "--cases") args.cases = argv[++i] ?? "";
    else if (argv[i] === "--workers") args.workers = Number(argv[++i] ?? 6);
    else if (argv[i] === "--no-judge") args.noJudge = true;
    else if (argv[i] === "--static-only") args.staticOnly = true;
  }
  return args;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));

  if (process.env.CHAOS === "1") {
    console.log("CHAOS=1 (flaky services + latency)\n");
  }

  process.env.REDTEAM_CANARY ??= REDTEAM_CANARY_VALUE;

  console.log("Static checks\n");
  const statics = await staticChecks();
  let staticPassed = 0;
  for (const { name, passed, detail } of statics) {
    console.log(`${passed ? "PASS" : "FAIL"}  [static] ${name} — ${detail}`);
    if (passed) staticPassed++;
  }
  console.log(`\n${staticPassed} / ${statics.length} static passed\n`);
  if (args.staticOnly) {
    return staticPassed === statics.length ? 0 : 1;
  }

  let cases = CASES.filter((c) => c.name.toLowerCase().includes(args.cases.toLowerCase()));
  const custom = (await loadCustomCases()).filter((c) => c.name.toLowerCase().includes(args.cases.toLowerCase()));
  if (custom.length > 0) {
    console.log(`Loaded ${custom.length} custom case(s) from evals/custom-cases.ts\n`);
  }
  cases = [...cases, ...custom];

  console.log("Retrieval probes (no LLM)\n");
  const probeOutcomes = await runProbes();
  let probesPassed = 0;
  for (const probe of probeOutcomes) {
    console.log(
      `${probe.passed ? "PASS" : "FAIL"}  [probe] ${JSON.stringify(probe.query)} -> want ${probe.expected}, got [${probe.ranked.join(", ")}]`,
    );
    if (probe.passed) probesPassed++;
  }
  console.log(`\n${probesPassed} / ${probeOutcomes.length} retrieval probes passed\n`);

  console.log("Agent Evaluation (v2)\n");
  let outcomes: EvalOutcome[];
  try {
    outcomes = await runEvaluation(cases, args.workers, args.noJudge);
  } catch (error) {
    if (error instanceof AgentConfigurationError) {
      console.error(`ERROR ${error.message}`);
      return 1;
    }
    throw error;
  }

  const passed = outcomes.filter((o) => o.passed).length;
  for (const outcome of outcomes) {
    if (args.verbose) {
      console.log(`\n[${outcome.case.category}] ${outcome.case.name}`);
      printVerbose(outcome);
    }
  }

  console.log(`\n${passed} / ${outcomes.length} LLM cases passed`);
  const byCategory = new Map<string, EvalOutcome[]>();
  for (const outcome of outcomes) {
    const key = outcome.case.category ?? "general";
    if (!byCategory.has(key)) byCategory.set(key, []);
    byCategory.get(key)!.push(outcome);
  }
  for (const category of [...byCategory.keys()].sort()) {
    const group = byCategory.get(category)!;
    console.log(`  ${category}: ${group.filter((o) => o.passed).length}/${group.length}`);
  }
  const judged = outcomes.map((o) => o.judgeScore).filter((s): s is number => s !== null);
  if (judged.length > 0) {
    console.log(`  avg judge score: ${(judged.reduce((a, b) => a + b, 0) / judged.length).toFixed(2)} (quality signal, non-gating)`);
  }
  const timingEntries = Object.entries(CASE_TIMINGS);
  if (timingEntries.length > 0) {
    const slowest = timingEntries.sort((a, b) => b[1] - a[1]).slice(0, 5);
    console.log("  slowest cases: " + slowest.map(([name, secs]) => `${name} (${secs.toFixed(0)}s)`).join(", "));
  }
  writeHtmlReport(outcomes, probeOutcomes, statics);
  console.log(`Updated ${HTML_REPORT_PATH}`);
  return 0;
}

runIfMain("src/eval.ts", main);
