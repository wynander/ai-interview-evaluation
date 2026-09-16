/**
 * Seed Postgres from canonical data + generated distractors.
 *
 * Usage:
 *     npx tsx src/db/seed.ts --distractors 3000
 *     npx tsx src/db/seed.ts --distractors 3000 --seed 999
 *     npx tsx src/db/seed.ts --counts-only
 *
 * Safe to re-run: truncates tables and re-seeds in one transaction, then
 * re-applies src/db/migrations/*.sql (candidate migrations) in sorted order.
 *
 * DATABASE_URL defaults to localhost (host dev) and is overridden in compose.
 */
import "dotenv/config";

import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Pool } from "pg";

import { generate as generateDistractors, seededRng } from "./generate-distractors";
import {
  CUSTOMERS,
  DOCUMENTATION,
  INCIDENTS,
  INITIAL_TICKETS,
  ORDERS,
  SUBSCRIPTIONS,
} from "../data";
import { runIfMain } from "../runtime-helpers";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");

const DEFAULT_DATABASE_URL = "postgresql://agent:agentdev@localhost:5432/support";

// One load-test customer with many orders to expose slow reads.
export const LOAD_CUSTOMER_ID = "C999";
export const LOAD_ORDER_COUNT = 15_000;

function databaseUrl(): string {
  return process.env.DATABASE_URL ?? DEFAULT_DATABASE_URL;
}

async function applySchema(client: { query: (text: string) => Promise<unknown> }): Promise<void> {
  const schema = readFileSync(join(ROOT, "src", "db", "schema.sql"), "utf-8");
  await client.query(schema);
  const migrations = readdirSync(join(ROOT, "src", "db", "migrations"))
    .filter((f) => f.endsWith(".sql"))
    .sort();
  for (const file of migrations) {
    await client.query(readFileSync(join(ROOT, "db", "migrations", file), "utf-8"));
  }
}

// Second customer so the core hops are tested against two entities — memorized
// answers for one fail on the other; only real joins + math + retrieval pass.
const EXTRA_CUSTOMER = {
  customer_id: "C555",
  name: "Priya Nair",
  email: "priya.nair@example.test",
  plan_code: "GRW",
  account_status: "active",
  product_code: "analytics",
  region_code: "NA",
  subscription_id: "SUB-555",
};
const EXTRA_SUBSCRIPTION = {
  subscription_id: "SUB-555",
  account: "555",
  started_on: "02/10/26",
  cycle: "A",
  status: "active",
};
const EXTRA_ORDERS = [
  {
    order_id: "O-5501",
    item: "Analytics Growth annual subscription",
    placed_on: "2025-11-20",
    status: "delivered",
    total_usd: 1800,
  },
  {
    order_id: "O-5502",
    item: "Additional workspace seats",
    placed_on: "2026-08-01",
    status: "delivered",
    total_usd: 240,
  },
];

export async function seed(
  canonicalSeed = 42,
  distractors = 3000,
  extraOrders = LOAD_ORDER_COUNT,
): Promise<Record<string, number>> {
  const distractorDocs = generateDistractors(canonicalSeed, distractors);
  const pool = new Pool({ connectionString: databaseUrl() });
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await applySchema(client);
    await client.query(
      "TRUNCATE customers, subscriptions, orders, documents, incidents, tickets, tool_audit_log RESTART IDENTITY",
    );

    for (const c of Object.values(CUSTOMERS)) {
      await client.query(
        "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)" +
          " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        [
          c.customer_id,
          c.name,
          c.email,
          c.plan_code,
          c.account_status,
          c.product_code,
          c.region_code,
          c.subscription_id,
          "Jan 5 2025",
        ],
      );
    }
    // Load-test customer for the big perf case.
    await client.query(
      "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)" +
        " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT DO NOTHING",
      [LOAD_CUSTOMER_ID, "Load Testerson", "load.test@example.test", "GRW", "active", "analytics", "NA", "SUB-999", "2025-01-05"],
    );
    await client.query(
      "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status)" +
        " VALUES ('SUB-999','999','01/05/25','A','active') ON CONFLICT DO NOTHING",
    );

    for (const s of Object.values(SUBSCRIPTIONS)) {
      await client.query(
        "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status) VALUES ($1,$2,$3,$4,$5)",
        [s.subscription_id, s.account, s.started_on, s.cycle, s.status],
      );
    }

    for (const o of Object.values(ORDERS)) {
      await client.query(
        "INSERT INTO orders (order_id, customer_id, item, placed_on, status, total_usd) VALUES ($1,$2,$3,$4,$5,$6)",
        [o.order_id, o.customer_id, o.item, o.placed_on, o.status, o.total_usd],
      );
    }

    // Bulk synthetic orders for the load customer. Mixed date formats on purpose.
    const rng = seededRng(canonicalSeed);
    const loadRows: Array<[string, string, string, string, string, number]> = [];
    for (let i = 0; i < extraOrders; i++) {
      const oid = `O-9${String(i).padStart(5, "0")}`;
      const fmt = rng();
      let placed: string;
      if (fmt < 0.7) {
        placed = `2026-${String(1 + Math.floor(rng() * 9)).padStart(2, "0")}-${String(1 + Math.floor(rng() * 28)).padStart(2, "0")}`;
      } else if (fmt < 0.9) {
        placed = `${String(1 + Math.floor(rng() * 12)).padStart(2, "0")}/${String(1 + Math.floor(rng() * 28)).padStart(2, "0")}/26`;
      } else {
        placed = `Aug ${1 + Math.floor(rng() * 28)} 2026`;
      }
      const status = rng() < 2 / 3 ? "delivered" : "processing";
      loadRows.push([oid, LOAD_CUSTOMER_ID, "Load-test line item", placed, status, 10 + Math.floor(rng() * 491)]);
    }
    // Multi-row batches (node-postgres has no COPY FROM STDIN helper).
    const BATCH = 500;
    for (let start = 0; start < loadRows.length; start += BATCH) {
      const batch = loadRows.slice(start, start + BATCH);
      const values: unknown[] = [];
      const placeholders = batch
        .map((row) => {
          const base = values.length;
          values.push(...row);
          return `($${base + 1},$${base + 2},$${base + 3},$${base + 4},$${base + 5},$${base + 6})`;
        })
        .join(",");
      await client.query(
        `INSERT INTO orders (order_id, customer_id, item, placed_on, status, total_usd) VALUES ${placeholders}`,
        values,
      );
    }

    for (const d of DOCUMENTATION) {
      await client.query(
        "INSERT INTO documents (doc_id, title, body, status, trust, effective_from, audience, version)" +
          " VALUES ($1,$2,$3,$4,$5,$6,'customer_facing',1)",
        [d.doc_id, d.title, d.body, d.status ?? "current", d.trust ?? "official", d.effective_from ?? "2024-01-01"],
      );
    }
    for (const d of distractorDocs) {
      await client.query(
        "INSERT INTO documents (doc_id, title, body, status, trust, effective_from, audience, version)" +
          " VALUES ($1,$2,$3,$4,$5,$6,$7,1)",
        [d.doc_id, d.title, d.body, d.status, d.trust, d.effective_from, d.audience],
      );
    }

    for (const inc of INCIDENTS) {
      await client.query(
        "INSERT INTO incidents (incident_id, service, region, status, severity, title, started_on, summary)" +
          " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        [inc.incident_id, inc.service, inc.region, inc.status, inc.severity, inc.title, inc.started_on, inc.summary],
      );
    }

    for (const t of INITIAL_TICKETS) {
      await client.query(
        "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id)" +
          " VALUES ($1,$2,$3,$4,$5,$6)",
        [t.ticket_id, t.customer_id, t.issue, t.priority, t.status, t.related_order_id],
      );
    }

    const c = EXTRA_CUSTOMER;
    await client.query(
      "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)" +
        " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
      [c.customer_id, c.name, c.email, c.plan_code, c.account_status, c.product_code, c.region_code, c.subscription_id, "Nov 20 2025"],
    );
    const s = EXTRA_SUBSCRIPTION;
    await client.query(
      "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status) VALUES ($1,$2,$3,$4,$5)",
      [s.subscription_id, s.account, s.started_on, s.cycle, s.status],
    );
    for (const o of EXTRA_ORDERS) {
      await client.query(
        "INSERT INTO orders (order_id, customer_id, item, placed_on, status, total_usd) VALUES ($1,$2,$3,$4,$5,$6)",
        [o.order_id, EXTRA_CUSTOMER.customer_id, o.item, o.placed_on, o.status, o.total_usd],
      );
    }
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
    await pool.end();
  }

  return counts();
}

export async function counts(): Promise<Record<string, number>> {
  const pool = new Pool({ connectionString: databaseUrl() });
  try {
    const out: Record<string, number> = {};
    for (const table of ["customers", "subscriptions", "orders", "documents", "incidents", "tickets"]) {
      const result = await pool.query(`SELECT count(*) FROM ${table}`);
      out[table] = Number(result.rows[0]?.count ?? 0);
    }
    return out;
  } finally {
    await pool.end();
  }
}

function parseArgs(argv: string[]): { seed: number; distractors: number; extraOrders: number; countsOnly: boolean } {
  const args = { seed: 42, distractors: 3000, extraOrders: LOAD_ORDER_COUNT, countsOnly: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--seed") args.seed = Number(argv[++i]);
    else if (argv[i] === "--distractors") args.distractors = Number(argv[++i]);
    else if (argv[i] === "--extra-orders") args.extraOrders = Number(argv[++i]);
    else if (argv[i] === "--counts-only") args.countsOnly = true;
  }
  return args;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  if (args.countsOnly) {
    const result = await counts();
    for (const [table, count] of Object.entries(result)) console.log(`${table}: ${count}`);
    return 0;
  }
  const result = await seed(args.seed, args.distractors, args.extraOrders);
  for (const [table, count] of Object.entries(result)) console.log(`${table}: ${count}`);
  return 0;
}

// Run as CLI when invoked directly (`npx tsx src/db/seed.ts ...`).
runIfMain("src/db/seed.ts", main);
