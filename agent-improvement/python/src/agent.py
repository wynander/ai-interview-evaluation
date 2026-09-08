"""Support agent definition and fixed model configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from .runtime_helpers import (
    content_as_text,
    friendly_model_error,
    records_from_messages,
)
from .tools import TOOLS

OPENAI_BASE_URL = "https://ai-gateway.vercel.sh/v1"
OPENAI_MODEL = "deepseek/deepseek-v4-flash-0731"

SYSTEM_PROMPT = """You are a support assistant for a software company.

Be helpful, concise, and professional. Use the available tools when they seem
useful. For account or order questions, look up the relevant records. Search
the support documentation when the user asks about a policy or process. If a
user describes a problem, create a support ticket to help move it forward.
If a tool returns no result, do your best to answer. You may make reasonable
assumptions when details are missing.
"""


class AgentConfigurationError(RuntimeError):
    """Raised when the exercise cannot be configured to call the model."""


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: str | None = None


@dataclass
class AgentResult:
    response: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    error: str | None = None


def build_model() -> ChatOpenAI:
    """Build the fixed model client used by the exercise."""

    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise AgentConfigurationError(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and add "
            "the short-lived Vercel AI Gateway key provided for the interview."
        )

    return ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=api_key,
        base_url=OPENAI_BASE_URL,
    )


class AgentSession:
    """A conversation with one support agent instance."""

    def __init__(self, model: Any | None = None):
        self._agent = create_agent(
            model=model or build_model(),
            tools=TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )
        self._messages: list[Any] = []

    def run(self, user_input: str) -> AgentResult:
        self._messages.append(HumanMessage(content=user_input))
        previous_message_count = len(self._messages) - 1
        state_messages = list(self._messages)
        error: str | None = None
        try:
            for chunk in self._agent.stream(
                {"messages": self._messages},
                config={"recursion_limit": 20},
                stream_mode="values",
            ):
                state_messages = list(chunk["messages"])
        except Exception as exc:
            error = friendly_model_error(exc)

        self._messages = state_messages
        records = records_from_messages(self._messages[previous_message_count:])
        response = ""
        for message in reversed(self._messages):
            if isinstance(message, AIMessage):
                response = content_as_text(message.content).strip()
                if response:
                    break

        if error and not response:
            response = "I couldn't complete that request."

        return AgentResult(response=response, tool_calls=records, error=error)


def run_agent(user_input: str, session: AgentSession | None = None) -> AgentResult:
    """Run one message, optionally continuing an existing conversation."""

    active_session = session or AgentSession()
    return active_session.run(user_input)
