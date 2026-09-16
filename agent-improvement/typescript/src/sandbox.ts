/**
 * Sandboxed code/SQL execution for the agent — 0-1 BUILD.
 *
 * The starter guards are weak by design. Red-team evals will try to break
 * out of both tools: harden them without breaking legit use, and add your
 * own attack cases in evals/custom-cases.ts.
 *
 * Red-team evals never execute hostile statements against your DB: they
 * check rejection at parse/plan stage plus unchanged row counts.
 */
import { tool, zodSchema } from "ai";
import { Pool } from "pg";
import vm from "node:vm";
import { z } from "zod";

import { databaseUrl, execute } from "./db";
import { asJson } from "./runtime-helpers";

export const BLOCKED_PATTERNS = [
  "\\bprocess\\b",
  "\\brequire\\s*\\(",
  "\\bimport\\s*\\(",
  "\\bimport\\b",
  "\\bexport\\b",
  "\\bfetch\\b",
  "\\beval\\s*\\(",
  "\\bFunction\\s*\\(",
  "__proto__",
  "\\bconstructor\\b",
  "\\bprototype\\b",
];

const DENY_STATEMENTS = /\b(drop|delete|update|insert|alter|create|truncate|copy|grant|revoke|vacuum)\b/i;

export interface RunJsOutcome {
  ok: boolean;
  result: string;
}

/** Execute JS in a fresh vm context with a minimal global set and a 2s timeout. */
export function execJs(code: string): RunJsOutcome {
  const logs: string[] = [];
  const sandbox: Record<string, unknown> = {
    console: {
      log: (...args: unknown[]) => {
        logs.push(args.map((a) => String(a)).join(" "));
      },
    },
    Math,
    Date,
    JSON,
    result: undefined as unknown,
  };
  vm.createContext(sandbox);
  try {
    vm.runInContext(code, sandbox, { timeout: 2000 });
    const result = sandbox.result !== undefined ? sandbox.result : logs.join("\n");
    return { ok: true, result: String(result).slice(0, 2000) };
  } catch (error) {
    const name = error instanceof Error ? error.constructor.name : "Error";
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, result: `${name}: ${message}` };
  }
}

export const runJs = tool({
  description:
    "Run a small JavaScript snippet for calculations (date math, deadlines). " +
    "Sandboxed: 2s timeout, minimal globals (Date/Math/JSON), no I/O. " +
    "Set `result = ...` or use console.log().",
  inputSchema: zodSchema(
    z.object({
      code: z.string().describe("JavaScript snippet. Set `result = ...` or console.log(). 2s timeout."),
    }),
  ),
  execute: async ({ code }: { code: string }) => {
    for (const pattern of BLOCKED_PATTERNS) {
      if (new RegExp(pattern).test(code)) {
        return `Blocked: code matches deny pattern ${pattern}. Keep to Date/Math/JSON with no I/O.`;
      }
    }
    const outcome = execJs(code);
    await execute("INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('run_js', $1)", [
      asJson({ code: code.slice(0, 500) }),
    ]);
    if (outcome.ok) {
      return asJson({ ok: true, result: outcome.result });
    }
    return `Snippet failed: ${outcome.result}`;
  },
});

function isReadonlyQuery(query: string): { ok: boolean; reason: string } {
  const text = query.trim().replace(/;+$/, "");
  if (DENY_STATEMENTS.test(text)) {
    return { ok: false, reason: "writes/DDL are not allowed (SELECT/WITH/EXPLAIN only)" };
  }
  const first = text.split(/\s+/, 1)[0]?.toUpperCase() ?? "";
  if (!["SELECT", "WITH", "EXPLAIN"].includes(first)) {
    return { ok: false, reason: `only SELECT/WITH/EXPLAIN allowed, got ${first || "(empty)"}` };
  }
  return { ok: true, reason: "" };
}

export const runSql = tool({
  description: "Run a READ-ONLY SQL lookup (SELECT/WITH) or EXPLAIN plan over orders/customers/etc.",
  inputSchema: zodSchema(
    z.object({
      query: z
        .string()
        .describe(
          "Read-only SELECT/WITH over orders/customers/etc. Writes are rejected; the documents table is not accessible here (use search_docs).",
        ),
      dry_run: z.boolean().default(false).describe("If true, return EXPLAIN plan only without executing."),
    }),
  ),
  execute: async ({ query, dry_run = false }: { query: string; dry_run?: boolean }) => {
    const gate = isReadonlyQuery(query);
    if (!gate.ok) {
      return `Blocked: ${gate.reason}.`;
    }

    // Dedicated connection (not the shared pool): SET statement_timeout is
    // session-scoped, so it must not leak onto pooled connections.
    const pool = new Pool({ connectionString: databaseUrl(), max: 1 });
    try {
      const client = await pool.connect();
      try {
        await client.query("SET statement_timeout = '5s'");
        if (dry_run) {
          const planQuery = query.trim().toUpperCase().startsWith("EXPLAIN") ? query : `EXPLAIN ${query}`;
          const plan = await client.query(planQuery);
          return asJson({ dry_run: true, plan: plan.rows });
        }
        // TODO: enforce LIMIT if missing.
        const result = await client.query(query);
        const rows = result.rows.slice(0, 200);
        await execute("INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('run_sql', $1)", [
          asJson({ query: query.slice(0, 500) }),
        ]);
        return asJson({ rows, truncated_at: 200 });
      } finally {
        client.release();
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return `SQL failed: ${message}`;
    } finally {
      await pool.end();
    }
  },
});

export const SANDBOX_TOOLS = { run_js: runJs, run_sql: runSql };
