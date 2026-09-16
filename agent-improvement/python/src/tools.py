"""Tools exposed to the support agent — now backed by Postgres + mock APIs.

Each tool has a CANDIDATE TODO. The starter works but is naive:
  - search_docs: uses retrieval.search (which YOU rebuild in retrieval.py).
  - API tools: single GET, no pagination, no retry, no timeout handling,
    inconsistent error shapes leak to the model.
  - Tickets: direct DB, no list-before-create, no dedup, no confirmation,
    no audit. Fix in code + db/migrations/.

Keep tool NAMES stable (evals check traces). Improve schemas, descriptions,
normalization, retries, and side-effect safety.
"""

from __future__ import annotations

import os
import time
from typing import Literal

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from . import db
from .normalize import normalize_id, to_iso
from .retrieval import search as retrieval_search
from .runtime_helpers import as_json
from .tracing import log_tool_call

MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://localhost:8001")
MOCK_API_KEY = os.environ.get("MOCK_API_KEY", "dev-insecure-key")


def _api_get(path: str, params: dict | None = None) -> dict | list | str:
    """TODO (candidate): retries with backoff, timeouts, unified errors.

    Starter: one attempt, 10s timeout, raw error text on failure.
    Return parsed JSON on success, or an error string the model can act on.
    """
    started = time.time()
    try:
        response = httpx.get(
            f"{MOCK_API_URL}{path}",
            params=params or {},
            headers={
                "X-API-Key": MOCK_API_KEY,
                # Propagates CHAOS=1 into the mock-apis container (env set on
                # the eval process never reaches it). Keep sending this.
                "X-Chaos": "1" if os.environ.get("CHAOS") == "1" else "0",
            },
            timeout=10.0,
        )
        latency_ms = (time.time() - started) * 1000
        if response.status_code >= 400:
            log_tool_call("http_get", {"path": path}, latency_ms, False, response.text[:200])
            return f"API error {response.status_code} on {path}: {response.text[:300]}"
        log_tool_call("http_get", {"path": path}, latency_ms, True)
        return response.json()
    except Exception as exc:  # noqa: BLE001 — surfaced to model as actionable text
        latency_ms = (time.time() - started) * 1000
        log_tool_call("http_get", {"path": path}, latency_ms, False, str(exc)[:200])
        return f"API request to {path} failed: {exc}. You may retry once."


class SearchDocsInput(BaseModel):
    query: str = Field(description="Keywords or question to find in support documentation.")


@tool("search_docs", args_schema=SearchDocsInput)
def search_docs(query: str) -> str:
    """Search support documentation. Returns top chunks with doc_id citations.

    Prefer results with status=current and trust=official. Never quote
    internal-audience docs to customers. Cite doc_ids you rely on.
    """
    started = time.time()
    # Narrow starter window: with lexical ranking, top-3 rarely surfaces the
    # official doc among 3000 distractors. Widen deliberately once ranking and
    # filtering improve (see retrieval.py).
    chunks = retrieval_search(query, limit=3)
    log_tool_call("search_docs", {"query": query}, (time.time() - started) * 1000, True,
                  f"{len(chunks)} chunks")
    if not chunks:
        return "No documentation matched the query."
    return as_json([
        {
            "doc_id": c.doc_id, "title": c.title, "body": c.body,
            "status": c.status, "trust": c.trust,
            "effective_from": c.effective_from, "audience": c.audience,
        }
        for c in chunks
    ])


class ResolveCustomerInput(BaseModel):
    customer_id: str | None = Field(default=None, description="A customer ID like C123.")
    name: str | None = Field(default=None, description="Full or partial customer name.")
    email: str | None = Field(default=None, description="Exact customer email.")


@tool("resolve_customer", args_schema=ResolveCustomerInput)
def resolve_customer(
    customer_id: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> str:
    """Resolve a customer reference to account(s). May return multiple matches —
    if ambiguous, ask the user to disambiguate instead of picking one."""
    if customer_id:
        result = _api_get(f"/customers/{normalize_id(customer_id)}")
        if isinstance(result, dict) and result.get("customer_id"):
            return as_json({"status": "exact_match", "customer": {
                "customer_id": result["customer_id"], "name": result["name"], "email": result["email"]}})
        return as_json({"status": "not_found", "matches": []})

    needle = (name or email or "").strip()
    result = _api_get("/customers", {"search": needle})
    if isinstance(result, str):
        return result
    matches = result.get("customers", []) if isinstance(result, dict) else []
    if email:
        matches = [m for m in matches if m["email"].casefold() == email.strip().casefold()]
    if len(matches) == 1:
        return as_json({"status": "exact_match", "customer": matches[0]})
    if len(matches) > 1:
        return as_json({"status": "ambiguous", "matches": matches})
    return as_json({"status": "not_found", "matches": []})


class CustomerInput(BaseModel):
    customer_id: str = Field(description="The customer ID, such as C123.")


@tool("get_customer", args_schema=CustomerInput)
def get_customer(customer_id: str) -> str:
    """Look up a full customer account record. IDs are upper-case, dates ISO."""
    result = _api_get(f"/customers/{normalize_id(customer_id)}")
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        result["customer_id"] = normalize_id(str(result.get("customer_id", "")))
        if result.get("created_at"):
            result["created_at"] = to_iso(str(result["created_at"]))
        return as_json(result)
    return as_json(result)


class SubscriptionInput(BaseModel):
    subscription_id: str = Field(description="The subscription ID, such as SUB-123.")


@tool("get_subscription", args_schema=SubscriptionInput)
def get_subscription(subscription_id: str) -> str:
    """Look up a subscription record by subscription ID (not customer ID)."""
    result = _api_get(f"/subscriptions/{subscription_id.strip()}")
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and result.get("started_on"):
        result["started_on"] = to_iso(str(result["started_on"]))
        return as_json(result)
    return as_json(result)


@tool("get_orders", args_schema=CustomerInput)
def get_orders(customer_id: str) -> str:
    """Get orders for a customer, newest first.

    TODO (candidate): this only fetches page 1 (50 rows). Handle pagination
    (next_cursor) and cap total rows so the 15k-order load customer doesn't
    blow context or time out. Consider summarizing (count + recent N).
    """
    result = _api_get("/orders", {"customer_id": normalize_id(customer_id), "limit": 50, "cursor": 0})
    if isinstance(result, str):
        return result
    orders = result.get("orders", []) if isinstance(result, dict) else []
    total = result.get("total") if isinstance(result, dict) else None
    for order in orders:
        order["customer_id"] = normalize_id(str(order.get("customer_id", "")))
        if order.get("placed_on"):
            order["placed_on"] = to_iso(str(order["placed_on"]))
    if isinstance(result, dict) and result.get("next_cursor") is not None:
        return as_json({"orders": orders, "total": total,
                        "note": f"showing 50 of {total}; pagination not yet implemented — see TODO"})
    return as_json(orders if total is None else {"orders": orders, "total": total})


class OrderInput(BaseModel):
    order_id: str = Field(description="The order ID, such as O-1042.")


@tool("get_order", args_schema=OrderInput)
def get_order(order_id: str) -> str:
    """Look up a single order by ID."""
    result = _api_get(f"/orders/{order_id.strip()}")
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if result.get("placed_on"):
            result["placed_on"] = to_iso(str(result["placed_on"]))
        return as_json(result)
    return as_json(result)


class IncidentInput(BaseModel):
    service: str = Field(description="Service name or code (e.g. collaboration, collab, migration).")
    region: str = Field(description="Region name or code (e.g. Europe, EU, APAC).")


@tool("get_active_incident", args_schema=IncidentInput)
def get_active_incident(service: str, region: str) -> str:
    """Find an active incident for a service + region. Codes and names both work."""
    result = _api_get("/incidents/active", {"service": service.strip(), "region": region.strip()})
    if isinstance(result, str):
        return result
    return as_json(result)


class TicketSearchInput(BaseModel):
    customer_id: str = Field(description="The customer ID.")
    order_id: str | None = Field(default=None, description="Optional order ID filter.")
    status: Literal["open", "pending", "closed"] | None = Field(default=None, description="Optional status filter.")


@tool("list_tickets", args_schema=TicketSearchInput)
def list_tickets(
    customer_id: str,
    order_id: str | None = None,
    status: Literal["open", "pending", "closed"] | None = None,
) -> str:
    """List support tickets for a customer. Call this before creating a ticket
    to avoid duplicates."""
    query = "SELECT ticket_id, customer_id, issue, priority, status, related_order_id FROM tickets WHERE upper(customer_id) = upper(%s)"
    params: list[str] = [customer_id.strip()]
    if order_id:
        query += " AND related_order_id = %s"
        params.append(order_id.strip().upper())
    if status:
        query += " AND status = %s"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT 50"
    rows = db.fetch_all(query, tuple(params))
    return as_json({"status": "ok", "tickets": rows})


class CreateTicketInput(BaseModel):
    customer_id: str = Field(description="The customer ID, such as C123.")
    issue: str = Field(description="Concise description of the issue.")
    priority: Literal["low", "normal", "high", "urgent"] = Field(default="normal", description="Ticket priority.")
    related_order_id: str | None = Field(default=None, description="Order ID to link, e.g. O-2014. Pass it when the user mentions an order.")


@tool("create_support_ticket", args_schema=CreateTicketInput)
def create_support_ticket(
    customer_id: str,
    issue: str,
    priority: Literal["low", "normal", "high", "urgent"] = "normal",
    related_order_id: str | None = None,
) -> str:
    """Create a support ticket.

    TODO (candidate): check list_tickets first and refuse likely dupes (point
    at the existing ticket instead). Add a DB unique constraint in
    db/migrations/ as backstop. Write an audit row to tool_audit_log.
    """
    normalized_customer = normalize_id(customer_id)
    cleaned_issue = issue.strip()
    if not cleaned_issue:
        return "Cannot create ticket: the issue description is empty."

    customer = db.fetch_one("SELECT customer_id FROM customers WHERE upper(customer_id) = upper(%s)", (normalized_customer,))
    if customer is None:
        return f"Cannot create ticket: no customer found for ID '{customer_id.strip()}'."

    row = db.fetch_one("SELECT nextval('ticket_seq') AS n")
    ticket_id = f"T-{int(row['n'])}" if row else "T-2001"
    db.execute(
        "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id)"
        " VALUES (%s,%s,%s,%s,'open',%s)",
        (ticket_id, normalized_customer, cleaned_issue, priority,
         related_order_id.strip().upper() if related_order_id else None),
    )
    db.execute(
        "INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('create_support_ticket', %s)",
        (as_json({"ticket_id": ticket_id, "customer_id": normalized_customer}),),
    )
    created = db.fetch_one("SELECT ticket_id, customer_id, issue, priority, status, related_order_id FROM tickets WHERE ticket_id = %s", (ticket_id,))
    return as_json(created)


TOOLS = [
    search_docs,
    resolve_customer,
    get_customer,
    get_subscription,
    get_orders,
    get_order,
    get_active_incident,
    list_tickets,
    create_support_ticket,
]
