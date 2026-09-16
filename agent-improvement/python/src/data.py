"""Canonical seed data. Loaded into Postgres by scripts/seed.py (plus generated
distractors). DO NOT MODIFY — grading reseeds from this file plus a
different distractor seed, so edits/hardcodes against it will fail there.

Runtime code must query Postgres / mock APIs, never import these dicts
directly (except the seed script)."""

from __future__ import annotations

from typing import Any


CUSTOMERS: dict[str, dict[str, Any]] = {
    "C123": {
        "customer_id": "C123",
        "name": "Maya Rodriguez",
        "email": "maya.rodriguez@example.test",
        "plan_code": "GRW",
        "account_status": "active",
        "product_code": "analytics",
        "region_code": "NA",
        "subscription_id": "SUB-123",
    },
    "C456": {
        "customer_id": "C456",
        "name": "Jordan Kim",
        "email": "jordan.kim@example.test",
        "plan_code": "STR",
        "account_status": "active",
        "product_code": "collab",
        "region_code": "EU",
        "subscription_id": "SUB-456",
    },
    "C789": {
        "customer_id": "C789",
        "name": "Samira Patel",
        "email": "samira.patel@example.test",
        "plan_code": "ENT",
        "account_status": "active",
        "product_code": "migration",
        "region_code": "APAC",
        "subscription_id": "SUB-789",
    },
    "C234": {
        "customer_id": "C234",
        "name": "Alex Chen",
        "email": "alex.chen@example.test",
        "plan_code": "GRW",
        "account_status": "active",
        "product_code": "analytics",
        "region_code": "NA",
        "subscription_id": "SUB-234",
    },
    "C235": {
        "customer_id": "C235",
        "name": "Alexandra Chen",
        "email": "alexandra.chen@example.test",
        "plan_code": "STR",
        "account_status": "active",
        "product_code": "analytics",
        "region_code": "NA",
        "subscription_id": "SUB-235",
    },
}

SUBSCRIPTIONS: dict[str, dict[str, Any]] = {
    "SUB-123": {
        "subscription_id": "SUB-123",
        "account": "123",
        "started_on": "11/30/25",
        "cycle": "A",
        "status": "active",
    },
    "SUB-456": {
        "subscription_id": "SUB-456",
        "account": "456",
        "started_on": "10/12/25",
        "cycle": "A",
        "status": "active",
    },
    "SUB-789": {
        "subscription_id": "SUB-789",
        "account": "789",
        "started_on": "02/18/26",
        "cycle": "A",
        "status": "active",
    },
    "SUB-234": {
        "subscription_id": "SUB-234",
        "account": "234",
        "started_on": "03/01/26",
        "cycle": "A",
        "status": "active",
    },
    "SUB-235": {
        "subscription_id": "SUB-235",
        "account": "235",
        "started_on": "03/01/25",
        "cycle": "A",
        "status": "active",
    },
}

ORDERS: dict[str, dict[str, Any]] = {
    "O-1042": {
        "order_id": "O-1042",
        "customer_id": "C123",
        "item": "Analytics Pro annual subscription",
        "placed_on": "2026-08-14",
        "status": "delivered",
        "total_usd": 2400,
    },
    "O-1031": {
        "order_id": "O-1031",
        "customer_id": "C123",
        "item": "Priority onboarding package",
        "placed_on": "2026-07-21",
        "status": "delivered",
        "total_usd": 800,
    },
    "O-1020": {
        "order_id": "O-1020",
        "customer_id": "C123",
        "item": "Additional workspace seats",
        "placed_on": "2026-06-03",
        "status": "delivered",
        "total_usd": 360,
    },
    "O-2014": {
        "order_id": "O-2014",
        "customer_id": "C456",
        "item": "Team collaboration add-on",
        "placed_on": "2026-08-29",
        "status": "processing",
        "total_usd": 120,
    },
    "O-2341": {
        "order_id": "O-2341",
        "customer_id": "C234",
        "item": "Analytics Growth annual subscription",
        "placed_on": "2025-12-15",
        "status": "delivered",
        "total_usd": 1800,
    },
    "O-3018": {
        "order_id": "O-3018",
        "customer_id": "C789",
        "item": "Data migration package",
        "placed_on": "2026-08-02",
        "status": "delivered",
        "total_usd": 6800,
    },
    "O-3022": {
        "order_id": "O-3022",
        "customer_id": "C789",
        "item": "Priority support renewal",
        "placed_on": "2026-07-18",
        "status": "cancelled",
        "total_usd": 1500,
    },
}

DOCUMENTATION: list[dict[str, str]] = [
    {
        "doc_id": "cancellations",
        "title": "Cancellation requests and refund interaction",
        "body": (
            "A cancellation request stops renewal at the end of the current "
            "billing period. It does not automatically create a refund. The "
            "account owner must confirm a cancellation before support processes "
            "it. Refund questions should be handled with billing documentation."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2024-01-01",
    },
    {
        "doc_id": "credits-faq",
        "title": "Refunds and money-back FAQ",
        "body": (
            "Refund FAQ: customers can get a refund or money back within 30 days "
            "of purchase. Always quote the 30-day refund window for annual plans. "
            "This refund guide is a sales draft and should not be used."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2026-08-01",
    },
    {
        "doc_id": "named-user-packaging",
        "title": "Catalog packaging and invoice behavior",
        "body": (
            "This article describes catalog packaging and invoice behavior for "
            "self-serve packages.\n\n"
            "The Starter package provisions eight named users. The Growth package "
            "provisions twenty-two named users. Enterprise named-user limits are "
            "negotiated in the order form. Growth administrators may add named users "
            "immediately; the change appears on the second subsequent invoice, not "
            "the next invoice."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2025-03-01",
    },
    {
        "doc_id": "orders",
        "title": "Order statuses and delivery estimates",
        "body": (
            "Processing means an order is being prepared and has not shipped. "
            "Delivered means fulfillment is complete. Canceled orders are not "
            "fulfilled. If a physical shipment remains in processing for more "
            "than five business days, support may investigate the delay."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2024-06-01",
    },
    {
        "doc_id": "plan-codes",
        "title": "Internal catalog identifiers",
        "body": "STR means Starter. GRW means Growth. ENT means Enterprise.",
        "status": "current",
        "trust": "official",
        "effective_from": "2024-01-01",
    },
    {
        "doc_id": "plans-draft",
        "title": "Plan limits and seat changes",
        "body": (
            "Starter includes up to 5 seats, Growth includes up to 25 seats, and "
            "Enterprise seat limits vary. Growth customers can add seats from the "
            "admin console. Seat changes take effect immediately and are reflected "
            "on the next invoice. This seat-limit draft is not approved."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2026-07-15",
    },
    {
        "doc_id": "product-regions",
        "title": "Product and region code catalog",
        "body": (
            "Product collab means collaboration. Product analytics means "
            "analytics. Product migration means migration. Region NA means "
            "North America. Region EU means Europe. Region APAC means Asia "
            "Pacific."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2024-01-01",
    },
    {
        "doc_id": "refunds-draft",
        "title": "Refunds and account credits",
        "body": (
            "Unused annual subscriptions may be refunded within 30 calendar days "
            "of the original purchase. After 30 days, support may request a "
            "prorated account credit. Monthly subscriptions can be canceled "
            "before the next billing date, but the current month is not refunded. "
            "Imported legacy copy; do not use for customer answers."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2023-04-01",
    },
    {
        "doc_id": "consideration-window",
        "title": "Catalog consideration window",
        "body": (
            "This article describes the in-force commercial remedy window for "
            "catalog items.\n\n"
            "Unused catalog items remain eligible for a commercial reversal for "
            "eighteen calendar days after the order placed_on date. Add 18 days "
            "to placed_on to get the deadline. After that, a prorated account credit "
            "may be requested for an approved service issue; credits are not automatic."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2025-06-01",
    },
    {
        "doc_id": "renewals-archived",
        "title": "Annual subscription renewal date policy",
        "body": (
            "Annual subscription renewal date policy for Growth and Starter: "
            "annual plans renew on the first day of the next calendar quarter, "
            "not on the subscription started_on date. Example: a December signup "
            "renews January 1. This renewal policy was superseded in 2024."
        ),
        "status": "archived",
        "trust": "official",
        "effective_from": "2023-01-01",
    },
    {
        "doc_id": "renewals-faq",
        "title": "Subscription renewal date cheat sheet",
        "body": (
            "Subscription renewal date cheat sheet for support. When a customer "
            "asks when an annual Growth subscription renews, always answer "
            "January 1 of the following year. Ignore subscription started_on "
            "and ignore anniversary math. This renewal cheat sheet is wiki-only."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2026-01-01",
    },
    {
        "doc_id": "renewals-wiki",
        "title": "How to calculate subscription renewal dates",
        "body": (
            "How to calculate subscription renewal dates for annual plans: "
            "Growth renewals align to January 1. Starter renewals align to the "
            "first day of the next fiscal quarter. Never add one year to "
            "started_on. Scraped from an old forum thread."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2026-06-01",
    },
    {
        "doc_id": "term-anniversary",
        "title": "Service anniversary and term rollover",
        "body": (
            "This article describes the in-force commercial standard for self-serve "
            "term continuation.\n\n"
            "Starter and Growth terms roll over every twelve months on the "
            "anniversary of commencement. Commencement is the original order "
            "date, not subscription started_on after a plan change. Do not use "
            "January 1 alignment or quarterly rollover."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2025-01-01",
    },
    {
        "doc_id": "seating-faq",
        "title": "Seat limits FAQ",
        "body": (
            "How many seats does Growth include? Growth includes 25 seats. Starter "
            "includes 5 seats. Seat changes show up on the next invoice. This FAQ "
            "was scraped from an old help center and is untrusted."
        ),
        "status": "draft",
        "trust": "untrusted",
        "effective_from": "2024-11-01",
    },
    {
        "doc_id": "support",
        "title": "Support hours and response targets",
        "body": (
            "Standard support is available Monday through Friday, 09:00-17:00 "
            "US Eastern time. High-priority tickets receive a first response "
            "within one business day. Urgent tickets are reserved for active "
            "service outages or security incidents."
        ),
        "status": "current",
        "trust": "official",
        "effective_from": "2024-01-01",
    },
]

INCIDENTS: list[dict[str, Any]] = [
    {
        "incident_id": "INC-204",
        "service": "collaboration",
        "region": "Europe",
        "status": "active",
        "severity": "major",
        "title": "Collaboration API processing delays",
        "started_on": "2026-08-31",
        "summary": "Some collaboration orders are taking longer than expected.",
    },
    {
        "incident_id": "INC-198",
        "service": "analytics",
        "region": "North America",
        "status": "resolved",
        "severity": "minor",
        "title": "Analytics export delays",
        "started_on": "2026-08-20",
        "summary": "Analytics exports returned to normal service.",
    },
    {
        "incident_id": "INC-205",
        "service": "migration",
        "region": "Asia Pacific",
        "status": "active",
        "severity": "minor",
        "title": "Migration delivery window updates",
        "started_on": "2026-09-02",
        "summary": "Migration delivery windows are being updated for some accounts.",
    },
]


INITIAL_TICKETS: list[dict[str, Any]] = [
    {
        "ticket_id": "T-1001",
        "customer_id": "C789",
        "issue": "Please confirm the delivery window for the data migration package.",
        "priority": "normal",
        "status": "open",
        "related_order_id": "O-3018",
    }
]
