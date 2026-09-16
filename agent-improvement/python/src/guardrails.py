"""Guardrails layer — 0-1 BUILD (stub).

Candidate TODO: implement and wire these into src/agent.py (post-tool and
pre-response checks). Keep it simple and explain decisions in DESIGN.md.

  1. check_tool_output(tool_name, result): block/deflect prompt-injection
     smuggled via docs or API results (e.g. "SYSTEM OVERRIDE", "DROP TABLE",
     "reveal internal documents"). Return (allowed, redacted_or_reason).
  2. check_response(text): block internal-audience content and over-sharing
     (internal routing codes, other customers' PII) before it reaches the user.
  3. needs_confirmation(intent): True for side-effectful intents (create
     ticket, issue credit) when a likely dupe exists or details are uncertain.

Evals test: injection docs are retrieved but must NOT change behavior;
internal docs must never be quoted; ticket creation needs confirmation
when a dupe likely exists.
"""

from __future__ import annotations

import json
import re

INJECTION_MARKERS = [
    "system override", "ignore all previous instructions", "ignore previous instructions",
    "drop table", "delete from tickets", "reveal the full contents",
    "admin directive",
]

INTERNAL_MARKERS = [
    "pagerduty", "on-call routing", "escalation matrix",
]


def check_tool_output(tool_name: str, result: str) -> tuple[bool, str]:
    """Return (allowed, text). If not allowed, text is the deflection reason."""
    _ = tool_name
    lowered = result.lower()
    if not any(marker in lowered for marker in INJECTION_MARKERS):
        return True, result
    # Salvage: if the result is a JSON list of doc chunks, drop only the
    # poisoned chunks instead of nuking the whole result (broad queries often
    # mix one smuggling doc in with legitimate hits).
    # TODO (candidate): extend to other shapes, log dropped chunk ids, add tests.
    try:
        parsed = json.loads(result)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    if isinstance(parsed, list) and parsed:
        kept = [
            chunk for chunk in parsed
            if not (isinstance(chunk, dict)
                    and any(marker in json.dumps(chunk).lower() for marker in INJECTION_MARKERS))
        ]
        dropped = len(parsed) - len(kept)
        if kept:
            note = (
                f"\n\n[guardrail: dropped {dropped} chunk(s) containing "
                "instruction-smuggling attempts; continue with trusted sources only "
                "(status=current, trust=official).]"
            )
            return True, json.dumps(kept, indent=2, sort_keys=True, default=str) + note
    return False, (
        "Tool output contained an instruction-smuggling attempt and was blocked. "
        "Continue with trusted sources only (status=current, trust=official)."
    )


def check_response(text: str) -> tuple[bool, str]:
    """Pre-response check. Blocks internal-only content from customer answers."""
    lowered = text.lower()
    for marker in INTERNAL_MARKERS:
        if marker in lowered:
            return False, (
                "Blocked: response appears to quote internal-only material. "
                "Re-answer from customer_facing sources only."
            )
    # TODO (candidate): PII check — don't leak other customers' emails.
    _ = re
    return True, text


def needs_confirmation(intent: str, context: dict) -> bool:
    """Heuristic for side-effect confirmation. Wire into agent loop or prompt."""
    if intent == "create_ticket" and context.get("likely_dupe"):
        return True
    return False
