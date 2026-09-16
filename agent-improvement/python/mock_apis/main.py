"""Mock external services (CRM / billing / incidents) backed by the same Postgres.

Intentionally has COMMON low-scale mistakes — not production-API trivia.
Candidate TODOs (see also src/tools.py client side):

  1. AUTH: accepts the default dev key forever, and allows missing keys with
     only a warning. Logs full request headers (leaks keys into logs).
     Fix: require a non-default key, reject missing/invalid with 401 JSON.
  2. ERRORS: some paths return plain-text 500s, others JSON. Clients can't
     rely on shape. Fix: always return JSON {detail, code, retryable}.
  3. PAGINATION: /orders is paginated (limit/cursor) but naive clients only
     fetch page 1. The load-test customer (C999, 15k orders) exposes this.
  4. FORMATS: IDs and dates pass through in mixed formats (c123 vs C123,
     MM/DD/YY vs ISO). Normalize in the tool layer, not here.
  5. No rate limiting / chaos handling on the server — chaos evals inject
     transient 503s + latency via the X-Chaos header (CHAOS=1). Your client
     should retry with backoff. Test with `make eval-chaos`.

Do NOT hide business logic here to make evals pass — the point is the agent
layer handles messy services gracefully.
"""

from __future__ import annotations

import os
import random
import time

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from decimal import Decimal
from datetime import date, datetime


def _jsonable(value):
    """Coerce DB types (Decimal, dates) to JSON-safe values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value

app = FastAPI(title="mock-apis")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://agent:agentdev@localhost:5432/support")
MOCK_API_KEY = os.environ.get("MOCK_API_KEY", "dev-insecure-key")

# Code aliases accepted directly — no vocab gotcha. Both forms work.
PRODUCT_ALIASES = {"collab": "collaboration", "analytics": "analytics", "migration": "migration",
                   "collaboration": "collaboration"}
REGION_ALIASES = {"NA": "North America", "EU": "Europe", "APAC": "Asia Pacific",
                  "North America": "North America", "Europe": "Europe", "Asia Pacific": "Asia Pacific",
                  "na": "North America", "eu": "Europe", "apac": "Asia Pacific"}


def _conn() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


def _check_auth(x_api_key: str | None, request: Request) -> None:
    # BAD (intentional): logs full headers including the key, allows missing keys.
    print(f"[mock-apis] headers={dict(request.headers)}", flush=True)
    if not x_api_key:
        print("[mock-apis] WARNING: missing API key, allowing anyway (fix me)", flush=True)
        return
    if x_api_key != MOCK_API_KEY:
        # Inconsistent error shape (intentional flaw #2).
        raise HTTPException(status_code=401, detail="bad api key")


def _chaos_enabled(request: Request) -> bool:
    # Chaos arrives via header (eval sets X-Chaos when CHAOS=1) because env
    # vars set on the eval process never reach this container. Server-side
    # CHAOS=1 also works (e.g. `CHAOS=1 docker compose up`).
    return request.headers.get("x-chaos") == "1" or os.environ.get("CHAOS") == "1"


def _maybe_flake(request: Request) -> None:
    # Transient failure rate under chaos so clients need retries with backoff.
    # At 30%, naive single-shot clients burn most of their step budget on
    # LLM-level re-asks. Disabled by default; chaos evals enable it.
    if _chaos_enabled(request) and random.random() < 0.30:
        raise HTTPException(status_code=503, detail="transient mock failure (retry me)")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/customers")
def list_customers(
    request: Request,
    search: str = Query(default=""),
    x_api_key: str | None = Header(default=None),
) -> JSONResponse:
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    needle = search.strip().casefold()
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT customer_id, name, email FROM customers")
        rows = [dict(r) for r in cur.fetchall()]
    if needle:
        rows = [r for r in rows
                if needle in r["name"].casefold() or needle in r["email"].casefold()
                or needle == r["customer_id"].casefold()]
    return JSONResponse(_jsonable({"customers": rows}))


@app.get("/customers/{customer_id}")
def get_customer(customer_id: str, request: Request, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    # Flaw: sometimes plain-text 500 on unknown IDs instead of JSON 404.
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM customers WHERE upper(customer_id) = upper(%s)", (customer_id.strip(),))
        row = cur.fetchone()
    if row is None:
        if random.random() < 0.5:
            return PlainTextResponse(f"no customer {customer_id}", status_code=500)
        raise HTTPException(status_code=404, detail=f"no customer {customer_id}")
    return JSONResponse(_jsonable(dict(row)))


@app.get("/subscriptions/{subscription_id}")
def get_subscription(subscription_id: str, request: Request, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM subscriptions WHERE subscription_id = %s", (subscription_id.strip(),))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no subscription {subscription_id}")
    return JSONResponse(_jsonable(dict(row)))


@app.get("/orders")
def list_orders(
    request: Request,
    customer_id: str = Query(default=""),
    limit: int = Query(default=50, le=200),
    cursor: int = Query(default=0),
    x_api_key: str | None = Header(default=None),
):
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    # Intentionally no ORDER BY index hint + offset pagination: slow for C999.
    # Naive clients fetch only page 1 (50 of 15k). Handle pagination client-side.
    if _chaos_enabled(request):
        time.sleep(random.uniform(0.1, 0.6))
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT count(*) AS n FROM orders WHERE upper(customer_id) = upper(%s)", (customer_id.strip(),))
        total = (cur.fetchone() or {"n": 0})["n"]
        cur.execute(
            "SELECT * FROM orders WHERE upper(customer_id) = upper(%s)"
            " ORDER BY placed_on DESC LIMIT %s OFFSET %s",
            (customer_id.strip(), limit, cursor),
        )
        rows = [dict(r) for r in cur.fetchall()]
    next_cursor = cursor + limit if cursor + limit < total else None
    return JSONResponse(_jsonable({"orders": rows, "total": total, "next_cursor": next_cursor}))


@app.get("/orders/{order_id}")
def get_order(order_id: str, request: Request, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id.strip(),))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no order {order_id}")
    return JSONResponse(_jsonable(dict(row)))


@app.get("/incidents/active")
def active_incident(
    request: Request,
    service: str = Query(default=""),
    region: str = Query(default=""),
    x_api_key: str | None = Header(default=None),
):
    _check_auth(x_api_key, request)
    _maybe_flake(request)
    svc = PRODUCT_ALIASES.get(service.strip(), service.strip().lower())
    reg = REGION_ALIASES.get(region.strip(), region.strip())
    with _conn() as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT * FROM incidents WHERE lower(service) = lower(%s) AND region = %s AND status = 'active' LIMIT 1",
            (svc, reg),
        )
        row = cur.fetchone()
    return JSONResponse(_jsonable({"status": "active" if row else "none", "incident": dict(row) if row else None}))
