/** Runtime helpers kept separate from the agent definition. */
import { execute, fetchOne } from "./db";

/**
 * Run `main` when this file is the CLI entry point (tsx / node), and exit
 * with its code. Keeps the `if __name__ == ...` equivalent in one place so
 * eval.ts, eval-retrieval.ts and seed.ts don't each hand-roll it.
 */
export function runIfMain(entrySuffix: string, main: () => Promise<number>): void {
  const invoked = (process.argv[1] ?? "").replace(/\\/g, "/").endsWith(entrySuffix);
  if (!invoked) return;
  main().then(
    (code) => process.exit(code),
    (error: unknown) => {
      console.error(error);
      process.exit(1);
    },
  );
}

export function asJson(value: unknown): string {
  // Keep DB types (dates) from crashing serialization.
  return JSON.stringify(
    value,
    (_key, val) => (val instanceof Date ? val.toISOString() : val),
    2,
  );
}

export function friendlyModelError(error: unknown): string {
  const message = String(error instanceof Error ? (error.stack ?? error.message) : error).toLowerCase();
  if (message.includes("401") || message.includes("unauthorized") || message.includes("authentication")) {
    return "The Vercel AI Gateway rejected the API key.";
  }
  if (message.includes("connect") || message.includes("timeout") || message.includes("network") || message.includes("fetch failed")) {
    return "The Vercel AI Gateway could not be reached. Check network access.";
  }
  if (message.includes("recursion limit") || message.includes("stopwhen") || message.includes("step count")) {
    return "Agent exceeded the step limit without finishing.";
  }
  return `The model request failed: ${error instanceof Error ? error.message : String(error)}`;
}

// --- Ticket helpers are DB-backed (v2). ---

/** Return the number of tickets in Postgres. */
export async function ticketCount(): Promise<number> {
  const row = await fetchOne<{ n: string }>("SELECT count(*) AS n FROM tickets");
  return row ? Number(row.n) : 0;
}

/** Restore seed ticket state: keep T-1001, drop everything created by evals. */
export async function resetTickets(): Promise<void> {
  await execute("DELETE FROM tickets WHERE ticket_id <> 'T-1001'");
  await execute(
    "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id)" +
      " VALUES ('T-1001','C789','Please confirm the delivery window for the data migration package.','normal','open','O-3018')" +
      " ON CONFLICT (ticket_id) DO NOTHING",
  );
}

/** Row counts for all seed tables — used by eval DB-invariant checks. */
export async function tableCounts(): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  for (const table of ["customers", "subscriptions", "orders", "documents", "incidents", "tickets"]) {
    const row = await fetchOne<{ n: string }>(`SELECT count(*) AS n FROM ${table}`);
    out[table] = row ? Number(row.n) : 0;
  }
  return out;
}
