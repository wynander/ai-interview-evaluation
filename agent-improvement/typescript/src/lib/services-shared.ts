/**
 * External services (CRM / billing / incidents) backed by the same Postgres.
 *
 * Intentionally has COMMON low-scale mistakes — not production-API trivia.
 * Candidate TODOs (see also src/tools.ts client side):
 *
 *  1. AUTH is broken: accepts anything, warns instead of rejecting, and logs
 *     full request headers (leaks keys into logs). Make it real.
 *  2. ERRORS: some paths return plain-text 500s, others JSON. Pick one shape
 *     clients can rely on.
 *  3. PAGINATION: /api/orders is paginated (limit/cursor); C999 has 15k orders.
 *  4. FORMATS: IDs and dates pass through in mixed formats (c123 vs C123,
 *     MM/DD/YY vs ISO).
 *  5. No rate limiting on the server — chaos evals inject transient 503s +
 *     latency via the X-Chaos header (CHAOS=1). Your client should survive
 *     them. Test with `make eval-chaos`. NEVER remove chaosEvaluation:
 *     the grading harness depends on it to test retry behavior.
 *
 * Do NOT hide business logic here to make evals pass — the point is the agent
 * layer handles messy services gracefully.
 */
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { Pool } from "pg";

const DATABASE_URL = process.env.DATABASE_URL ?? "postgresql://agent:agentdev@localhost:5432/support";
const SERVICES_API_KEY = process.env.SERVICES_API_KEY ?? "dev-insecure-key";

// Code aliases accepted directly — no vocab gotcha. Both forms work.
const PRODUCT_ALIASES: Record<string, string> = {
  collab: "collaboration",
  analytics: "analytics",
  migration: "migration",
  collaboration: "collaboration",
};
const REGION_ALIASES: Record<string, string> = {
  NA: "North America",
  EU: "Europe",
  APAC: "Asia Pacific",
  "North America": "North America",
  Europe: "Europe",
  "Asia Pacific": "Asia Pacific",
  na: "North America",
  eu: "Europe",
  apac: "Asia Pacific",
};

export function productAlias(value: string): string {
  return PRODUCT_ALIASES[value] ?? value.toLowerCase();
}

export function regionAlias(value: string): string {
  return REGION_ALIASES[value] ?? value;
}

let sharedPool: Pool | null = null;

export function servicesPool(): Pool {
  if (!sharedPool) {
    sharedPool = new Pool({ connectionString: DATABASE_URL, max: 10, connectionTimeoutMillis: 10_000 });
    // Idle-client errors crash node if unhandled — log and survive.
    sharedPool.on("error", (error) => console.error(`[services] pool error: ${error.message}`));
  }
  return sharedPool;
}

/** Auth error response, or null when the request is allowed through. */
export function checkAuth(request: NextRequest): NextResponse | null {
  // BAD (intentional): logs full headers including the key, allows missing keys.
  console.log(`[services] headers=${JSON.stringify(Object.fromEntries(request.headers))}`);
  const key = request.headers.get("x-api-key");
  if (!key) {
    console.log("[services] WARNING: missing API key, allowing anyway (fix me)");
    return null;
  }
  if (key !== SERVICES_API_KEY) {
    // Inconsistent error shape (intentional flaw #2).
    return NextResponse.json({ detail: "bad api key" }, { status: 401 });
  }
  return null;
}

export function chaosEnabled(request: NextRequest): boolean {
  // Chaos arrives via header (eval sets X-Chaos when CHAOS=1) because env
  // vars set on the eval process never reach this container. Server-side
  // CHAOS=1 also works (e.g. `CHAOS=1 docker compose up`).
  return request.headers.get("x-chaos") === "1" || process.env.CHAOS === "1";
}

/**
 * Transient failure response under chaos, or null to continue.
 *
 * NEVER REMOVE THIS. The grading harness (make eval-chaos) depends on it to
 * test whether your client retries transient failures. Removing it or
 * neutering the failure rate is graded as weakening the eval.
 */
export function chaosEvaluation(request: NextRequest): NextResponse | null {
  // Transient failure rate under chaos so clients need retries.
  // At 30%, naive single-shot clients burn most of their step budget on
  // LLM-level re-asks. Disabled by default; chaos evals enable it.
  if (chaosEnabled(request) && Math.random() < 0.3) {
    return NextResponse.json({ detail: "transient services failure (retry me)" }, { status: 503 });
  }
  return null;
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
