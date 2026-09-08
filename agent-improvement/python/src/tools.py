"""Tools exposed to the support agent."""

from __future__ import annotations

import re
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from .data import (
    CUSTOMERS,
    DOCUMENTATION,
    INCIDENTS,
    ORDERS,
    SUBSCRIPTIONS,
)
from .runtime_helpers import (
    as_json,
    get_support_tickets,
    next_ticket_id,
    normalize_identifier,
)


class SearchDocsInput(BaseModel):
    query: str = Field(description="Text to search for in support documentation.")


@tool("search_docs", args_schema=SearchDocsInput)
def search_docs(query: str) -> str:
    """Search the internal support documentation."""

    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not terms:
        return "No documentation matched the query."

    matches: list[tuple[int, dict[str, str]]] = []
    for document in DOCUMENTATION:
        document_terms = set(
            re.findall(
                r"[a-z0-9]+",
                f"{document['title']} {document['body']}".lower(),
            )
        )
        score = len(terms & document_terms)
        if score:
            matches.append((score, document))

    if not matches:
        return "No documentation matched the query."

    matches.sort(key=lambda item: (-item[0], item[1]["doc_id"]))
    return as_json(
        [
            {
                "doc_id": document["doc_id"],
                "title": document["title"],
                "snippet": document["body"][:90],
                "status": document.get("status", "current"),
                "trust": document.get("trust", "official"),
                "effective_from": document.get("effective_from"),
            }
            for _, document in matches[:3]
        ]
    )


class ResolveCustomerInput(BaseModel):
    customer_id: str | None = Field(default=None, description="A customer ID.")
    name: str | None = Field(default=None, description="The customer's name.")
    email: str | None = Field(default=None, description="The customer's email.")


@tool("resolve_customer", args_schema=ResolveCustomerInput)
def resolve_customer(
    customer_id: str | None = None,
    name: str | None = None,
    email: str | None = None,
) -> str:
    """Resolve a customer reference to an account."""

    if customer_id:
        customer = CUSTOMERS.get(normalize_identifier(customer_id))
        matches = [customer] if customer else []
    else:
        needle_name = name.strip().casefold() if name else None
        needle_email = email.strip().casefold() if email else None
        matches = [
            customer
            for customer in CUSTOMERS.values()
            if (
                needle_name is not None
                and needle_name in customer["name"].casefold()
            )
            or (
                needle_email is not None
                and customer["email"].casefold() == needle_email
            )
        ]

    if len(matches) == 1:
        customer = matches[0]
        return as_json(
            {
                "status": "exact_match",
                "customer": {
                    "customer_id": customer["customer_id"],
                    "name": customer["name"],
                    "email": customer["email"],
                },
            }
        )
    if len(matches) > 1:
        return as_json(
            {
                "status": "ambiguous",
                "matches": [
                    {
                        "customer_id": customer["customer_id"],
                        "name": customer["name"],
                        "email": customer["email"],
                    }
                    for customer in matches
                ],
            }
        )
    return as_json({"status": "not_found", "matches": []})


class CustomerInput(BaseModel):
    customer_id: str = Field(description="The customer ID, such as C123.")


@tool("get_customer", args_schema=CustomerInput)
def get_customer(customer_id: str) -> str:
    """Look up a customer account."""

    normalized_id = normalize_identifier(customer_id)
    customer = CUSTOMERS.get(normalized_id)
    if customer is None:
        return f"No customer found for customer ID '{customer_id.strip()}'."
    return as_json(customer)


class SubscriptionInput(BaseModel):
    subscription_id: str = Field(description="The subscription ID.")


@tool("get_subscription", args_schema=SubscriptionInput)
def get_subscription(subscription_id: str) -> str:
    """Look up a subscription record."""

    normalized_id = normalize_identifier(subscription_id)
    subscription = SUBSCRIPTIONS.get(normalized_id)
    if subscription is None:
        return f"No subscription found for subscription ID '{subscription_id.strip()}'."
    return as_json(subscription)


@tool("get_orders", args_schema=CustomerInput)
def get_orders(customer_id: str) -> str:
    """Get orders for a customer."""

    normalized_id = normalize_identifier(customer_id)
    if normalized_id not in CUSTOMERS:
        return f"No customer found for customer ID '{customer_id.strip()}'."

    orders = [
        order
        for order in ORDERS.values()
        if order["customer_id"] == normalized_id
    ]
    orders.sort(key=lambda order: order["placed_on"], reverse=True)
    if not orders:
        return f"No orders found for customer ID '{normalized_id}'."
    return as_json(orders)


class OrderInput(BaseModel):
    order_id: str = Field(description="The order ID, such as O-1042.")


@tool("get_order", args_schema=OrderInput)
def get_order(order_id: str) -> str:
    """Look up an order by ID."""

    order = ORDERS.get(order_id.strip())
    if order is None:
        return f"No order found for order ID '{order_id.strip()}'."
    return as_json(order)


class IncidentInput(BaseModel):
    service: str = Field(description="The service name.")
    region: str = Field(description="The region name.")


@tool("get_active_incident", args_schema=IncidentInput)
def get_active_incident(service: str, region: str) -> str:
    """Find an active incident affecting a service and region."""

    incident = next(
        (
            incident
            for incident in INCIDENTS
            if incident["service"].casefold() == service.strip().casefold()
            and incident["region"].casefold() == region.strip().casefold()
            and incident["status"] == "active"
        ),
        None,
    )
    return as_json(
        {
            "status": "active" if incident else "none",
            "incident": incident,
        }
    )


class TicketSearchInput(BaseModel):
    customer_id: str = Field(description="The customer ID.")
    order_id: str | None = Field(default=None, description="An optional order ID.")
    status: Literal["open", "pending", "closed"] | None = Field(
        default=None,
        description="An optional ticket status.",
    )


@tool("list_tickets", args_schema=TicketSearchInput)
def list_tickets(
    customer_id: str,
    order_id: str | None = None,
    status: Literal["open", "pending", "closed"] | None = None,
) -> str:
    """List support tickets for a customer."""

    normalized_customer_id = normalize_identifier(customer_id)
    tickets = [
        ticket
        for ticket in get_support_tickets()
        if ticket["customer_id"] == normalized_customer_id
        and (
            order_id is None
            or ticket.get("related_order_id") == order_id.strip().upper()
        )
        and (status is None or ticket["status"] == status)
    ]
    return as_json({"status": "ok", "tickets": tickets})


class CreateTicketInput(BaseModel):
    customer_id: str = Field(description="The customer ID, such as C123.")
    issue: str = Field(description="A concise description of the issue.")
    priority: Literal["low", "normal", "high", "urgent"] = Field(
        default="normal",
        description="Ticket priority.",
    )
    related_order_id: str | None = Field(
        default=None,
        description="Optional reference id.",
    )


@tool("create_support_ticket", args_schema=CreateTicketInput)
def create_support_ticket(
    customer_id: str,
    issue: str,
    priority: Literal["low", "normal", "high", "urgent"] = "normal",
    related_order_id: str | None = None,
) -> str:
    """Create a support ticket for a customer."""

    normalized_id = normalize_identifier(customer_id)
    if normalized_id not in CUSTOMERS:
        return f"Cannot create ticket: no customer found for ID '{customer_id.strip()}'."

    cleaned_issue = issue.strip()
    if not cleaned_issue:
        return "Cannot create ticket: the issue description is empty."

    ticket = {
        "ticket_id": next_ticket_id(),
        "customer_id": normalized_id,
        "issue": cleaned_issue,
        "priority": priority,
        "status": "open",
    }
    if related_order_id:
        ticket["related_order_id"] = related_order_id.strip().upper()
    get_support_tickets().append(ticket)
    return as_json(ticket)


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
