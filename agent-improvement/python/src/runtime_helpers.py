"""Runtime helpers kept separate from the agent definition."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage


def normalize_identifier(value: str) -> str:
    return value.strip().upper()


def as_json(value: object) -> str:
    # default=str keeps DB types (Decimal, dates) from crashing serialization.
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content) if content is not None else ""


def friendly_model_error(error: Exception) -> str:
    message = str(error).lower()
    if "401" in message or "unauthorized" in message or "authentication" in message:
        return "The Vercel AI Gateway rejected the API key."
    if "connect" in message or "timeout" in message or "network" in message:
        return "The Vercel AI Gateway could not be reached. Check network access."
    if "recursion limit" in message:
        return "Agent exceeded the step limit without finishing."
    return f"The model request failed: {error}"


def records_from_messages(messages: list[Any]) -> list[Any]:
    from .agent import ToolCallRecord

    results_by_id: dict[str, str] = {}
    for message in messages:
        if isinstance(message, ToolMessage):
            tool_call_id = getattr(message, "tool_call_id", None)
            if tool_call_id:
                results_by_id[tool_call_id] = content_as_text(message.content)

    records: list[ToolCallRecord] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            call_id = call.get("id")
            records.append(
                ToolCallRecord(
                    name=call.get("name", ""),
                    arguments=call.get("args", {}),
                    result=results_by_id.get(call_id),
                )
            )
    return records


# --- Ticket helpers are now DB-backed (v2). ---

def ticket_count() -> int:
    """Return the number of tickets in Postgres."""
    from . import db

    row = db.fetch_one("SELECT count(*) AS n FROM tickets")
    return int(row["n"]) if row else 0


def reset_tickets() -> None:
    """Restore seed ticket state: keep T-1001, drop everything created by evals."""
    from . import db

    db.execute("DELETE FROM tickets WHERE ticket_id <> 'T-1001'")
    db.execute(
        "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id)"
        " VALUES ('T-1001','C789','Please confirm the delivery window for the data migration package.','normal','open','O-3018')"
        " ON CONFLICT (ticket_id) DO NOTHING"
    )


def table_counts() -> dict[str, int]:
    """Row counts for all seed tables — used by eval DB-invariant checks."""
    from . import db

    out: dict[str, int] = {}
    for table in ("customers", "subscriptions", "orders", "documents", "incidents", "tickets"):
        row = db.fetch_one(f"SELECT count(*) AS n FROM {table}")
        out[table] = int(row["n"]) if row else 0
    return out
