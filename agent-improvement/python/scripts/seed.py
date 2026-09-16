"""Seed Postgres from canonical data + generated distractors.

Usage:
    uv run python -m scripts.seed --distractors 3000
    uv run python -m scripts.seed --distractors 3000 --seed 999
    uv run python -m scripts.seed --counts-only

Safe to re-run: truncates tables and re-seeds in one transaction, then
re-applies db/migrations/*.sql (candidate migrations) in sorted order.

DATABASE_URL defaults to localhost (host dev) and is overridden in compose.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.generate_distractors import generate as generate_distractors  # noqa: E402

DEFAULT_DATABASE_URL = "postgresql://agent:agentdev@localhost:5432/support"

# One load-test customer with many orders to make naive SELECT * + N+1 slow.
# This is a BIG perf problem on purpose — fix with an index + LIMIT/JOIN.
LOAD_CUSTOMER_ID = "C999"
LOAD_ORDER_COUNT = 15_000


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def apply_schema(conn: psycopg.Connection) -> None:
    schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema)
    migrations = sorted((ROOT / "db" / "migrations").glob("*.sql"))
    with conn.cursor() as cur:
        for path in migrations:
            cur.execute(path.read_text(encoding="utf-8"))


# Second customer so the core hops are tested against two entities — memorized
# answers for one fail on the other; only real joins + math + retrieval pass.
EXTRA_CUSTOMER = {
    "customer_id": "C555", "name": "Priya Nair", "email": "priya.nair@example.test",
    "plan_code": "GRW", "account_status": "active", "product_code": "analytics",
    "region_code": "NA", "subscription_id": "SUB-555",
}
EXTRA_SUBSCRIPTION = {"subscription_id": "SUB-555", "account": "555", "started_on": "02/10/26", "cycle": "A", "status": "active"}
EXTRA_ORDERS = [
    {"order_id": "O-5501", "item": "Analytics Growth annual subscription", "placed_on": "2025-11-20", "status": "delivered", "total_usd": 1800},
    {"order_id": "O-5502", "item": "Additional workspace seats", "placed_on": "2026-08-01", "status": "delivered", "total_usd": 240},
]


def seed(canonical_seed: int = 42, distractors: int = 3000, extra_orders: int = LOAD_ORDER_COUNT) -> dict[str, int]:
    from src.data import CUSTOMERS, DOCUMENTATION, INCIDENTS, INITIAL_TICKETS, ORDERS, SUBSCRIPTIONS

    distractor_docs = generate_distractors(seed=canonical_seed, count=distractors)

    with psycopg.connect(database_url(), autocommit=False) as conn:
        apply_schema(conn)
        with conn.cursor() as cur:
            cur.execute("TRUNCATE customers, subscriptions, orders, documents, incidents, tickets, tool_audit_log RESTART IDENTITY")

            for c in CUSTOMERS.values():
                cur.execute(
                    "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (c["customer_id"], c["name"], c["email"], c["plan_code"], c["account_status"],
                     c["product_code"], c["region_code"], c["subscription_id"], "Jan 5 2025"),
                )
            # Load-test customer for the big perf case.
            cur.execute(
                "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (LOAD_CUSTOMER_ID, "Load Testerson", "load.test@example.test", "GRW", "active",
                 "analytics", "NA", "SUB-999", "2025-01-05"),
            )
            cur.execute(
                "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status)"
                " VALUES ('SUB-999','999','01/05/25','A','active') ON CONFLICT DO NOTHING"
            )

            for s in SUBSCRIPTIONS.values():
                cur.execute(
                    "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status)"
                    " VALUES (%s,%s,%s,%s,%s)",
                    (s["subscription_id"], s["account"], s["started_on"], s["cycle"], s["status"]),
                )

            for o in ORDERS.values():
                cur.execute(
                    "INSERT INTO orders (order_id, customer_id, item, placed_on, status, total_usd)"
                    " VALUES (%s,%s,%s,%s,%s,%s)",
                    (o["order_id"], o["customer_id"], o["item"], o["placed_on"], o["status"], o["total_usd"]),
                )

            # Bulk synthetic orders for the load customer. Mixed date formats on purpose.
            rng = random.Random(canonical_seed)
            load_rows = []
            for i in range(extra_orders):
                oid = f"O-9{i:05d}"
                fmt = rng.random()
                if fmt < 0.7:
                    placed = f"2026-{rng.randint(1, 9):02d}-{rng.randint(1, 28):02d}"
                elif fmt < 0.9:
                    placed = f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/26"
                else:
                    placed = f"Aug {rng.randint(1, 28)} 2026"
                load_rows.append((oid, LOAD_CUSTOMER_ID, "Load-test line item", placed,
                                  rng.choice(["delivered", "delivered", "processing"]), rng.randint(10, 500)))
            with cur.copy("COPY orders (order_id, customer_id, item, placed_on, status, total_usd) FROM STDIN") as copy:
                for row in load_rows:
                    copy.write_row(row)

            for d in DOCUMENTATION:
                cur.execute(
                    "INSERT INTO documents (doc_id, title, body, status, trust, effective_from, audience, version)"
                    " VALUES (%s,%s,%s,%s,%s,%s,'customer_facing',1)",
                    (d["doc_id"], d["title"], d["body"], d.get("status", "current"),
                     d.get("trust", "official"), d.get("effective_from", "2024-01-01")),
                )
            for d in distractor_docs:
                cur.execute(
                    "INSERT INTO documents (doc_id, title, body, status, trust, effective_from, audience, version)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                    (d["doc_id"], d["title"], d["body"], d["status"], d["trust"],
                     d["effective_from"], d["audience"]),
                )

            for inc in INCIDENTS:
                cur.execute(
                    "INSERT INTO incidents (incident_id, service, region, status, severity, title, started_on, summary)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (inc["incident_id"], inc["service"], inc["region"], inc["status"],
                     inc["severity"], inc["title"], inc["started_on"], inc["summary"]),
                )

            for t in INITIAL_TICKETS:
                cur.execute(
                    "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id)"
                    " VALUES (%s,%s,%s,%s,%s,%s)",
                    (t["ticket_id"], t["customer_id"], t["issue"], t["priority"],
                     t["status"], t.get("related_order_id")),
                )

            c = EXTRA_CUSTOMER
            cur.execute(
                "INSERT INTO customers (customer_id, name, email, plan_code, account_status, product_code, region_code, subscription_id, created_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (c["customer_id"], c["name"], c["email"], c["plan_code"], c["account_status"],
                 c["product_code"], c["region_code"], c["subscription_id"], "Nov 20 2025"),
            )
            s = EXTRA_SUBSCRIPTION
            cur.execute(
                "INSERT INTO subscriptions (subscription_id, account, started_on, cycle, status)"
                " VALUES (%s,%s,%s,%s,%s)",
                (s["subscription_id"], s["account"], s["started_on"], s["cycle"], s["status"]),
            )
            for o in EXTRA_ORDERS:
                cur.execute(
                    "INSERT INTO orders (order_id, customer_id, item, placed_on, status, total_usd)"
                    " VALUES (%s,%s,%s,%s,%s,%s)",
                    (o["order_id"], EXTRA_CUSTOMER["customer_id"], o["item"],
                     o["placed_on"], o["status"], o["total_usd"]),
                )
        conn.commit()

    return counts()


def counts() -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(database_url()) as conn, conn.cursor() as cur:
        for table in ("customers", "subscriptions", "orders", "documents", "incidents", "tickets"):
            cur.execute(f"SELECT count(*) FROM {table}")
            row = cur.fetchone()
            out[table] = int(row[0]) if row else 0
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--distractors", type=int, default=3000)
    parser.add_argument("--extra-orders", type=int, default=LOAD_ORDER_COUNT)
    parser.add_argument("--counts-only", action="store_true")
    args = parser.parse_args()

    if args.counts_only:
        for table, count in counts().items():
            print(f"{table}: {count}")
        return 0

    result = seed(canonical_seed=args.seed, distractors=args.distractors, extra_orders=args.extra_orders)
    for table, count in result.items():
        print(f"{table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
