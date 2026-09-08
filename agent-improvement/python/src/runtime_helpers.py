"""Runtime helpers kept separate from the agent definition."""

from __future__ import annotations

import json
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from .data import INITIAL_TICKETS


def normalize_identifier(value: str) -> str:
    return value.strip().upper()


def as_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


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


_ticket_state: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "ticket_state",
    default=None,
)
_ticket_counter: ContextVar[int | None] = ContextVar(
    "ticket_counter",
    default=None,
)


def get_support_tickets() -> list[dict[str, Any]]:
    """Return the current context's process-local ticket list."""

    tickets = _ticket_state.get()
    if tickets is None:
        tickets = deepcopy(INITIAL_TICKETS)
        _ticket_state.set(tickets)
    return tickets


def ticket_count() -> int:
    """Return the number of tickets in the current context."""

    return len(get_support_tickets())


def reset_tickets() -> None:
    """Restore the initial process-local ticket state."""

    _ticket_state.set(deepcopy(INITIAL_TICKETS))
    _ticket_counter.set(1002)


def next_ticket_id() -> str:
    """Return a new ticket ID and advance the process-local counter."""

    next_number = _ticket_counter.get()
    if next_number is None:
        next_number = 1002
    ticket_id = f"T-{next_number}"
    _ticket_counter.set(next_number + 1)
    return ticket_id
