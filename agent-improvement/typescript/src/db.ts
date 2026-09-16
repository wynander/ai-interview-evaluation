/** DB connection helpers. Single place for pooling + URL handling. */
import "dotenv/config";

import { drizzle, type NodePgDatabase } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

import * as schema from "./db/schema";

export const DEFAULT_DATABASE_URL =
  "postgresql://agent:agentdev@localhost:5432/support";
export const DEFAULT_AGENT_DATABASE_URL =
  "postgresql://agent_readonly:readonlydev@localhost:5432/support";

export function databaseUrl(): string {
  return process.env.DATABASE_URL ?? DEFAULT_DATABASE_URL;
}

/** Connection URL for the read-only agent_readonly role. */
export function agentDatabaseUrl(): string {
  return process.env.AGENT_DATABASE_URL ?? DEFAULT_AGENT_DATABASE_URL;
}

const pools = new Map<string, Pool>();
const clients = new Map<string, NodePgDatabase<typeof schema>>();

/** Return a small shared pool. Candidate TODO: tune min/max size + timeouts. */
export function pool(readonly = false): Pool {
  const key = readonly ? "ro" : "rw";
  let existing = pools.get(key);
  if (!existing) {
    existing = new Pool({
      connectionString: readonly ? agentDatabaseUrl() : databaseUrl(),
      min: 1,
      max: 5,
      connectionTimeoutMillis: 10_000,
    });
    pools.set(key, existing);
  }
  return existing;
}

export function db(readonly = false): NodePgDatabase<typeof schema> {
  const key = readonly ? "ro" : "rw";
  let existing = clients.get(key);
  if (!existing) {
    existing = drizzle(pool(readonly), { schema });
    clients.set(key, existing);
  }
  return existing;
}

export async function fetchAll<T = Record<string, unknown>>(
  query: string,
  params: unknown[] = [],
): Promise<T[]> {
  const result = await pool().query(query, params as never[]);
  return result.rows as T[];
}

export async function fetchOne<T = Record<string, unknown>>(
  query: string,
  params: unknown[] = [],
): Promise<T | null> {
  const rows = await fetchAll<T>(query, params);
  return rows[0] ?? null;
}

export async function execute(query: string, params: unknown[] = []): Promise<number> {
  const result = await pool().query(query, params as never[]);
  return result.rowCount ?? 0;
}

/** Fast failure if Postgres is unreachable (avoids slow pool timeouts). */
export async function ping(connectTimeoutMs = 3000): Promise<void> {
  const probe = new Pool({
    connectionString: databaseUrl(),
    connectionTimeoutMillis: connectTimeoutMs,
    max: 1,
  });
  try {
    await probe.query("SELECT 1");
  } finally {
    await probe.end();
  }
}
