"""Minimal JSONL tracing + token/cost counters.

Starter only logs tool calls. Candidate TODO:
  - Log model calls (tokens in/out, latency, est. cost) from src/agent.py.
  - Add a `traces/summary.py` or note in DESIGN.md: avg tool calls / case,
    avg latency, est. cost per 100 eval runs.
  - Redact secrets (API keys, emails?) before writing. Eval checks that
    OPENAI_API_KEY never appears in traces/.

Keep it dependency-free and human-readable (one JSON object per line).
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

TRACES_DIR = Path(__file__).resolve().parent.parent / "traces"
SECRET_MARKER = "OPENAI_API_KEY"


def _redact(text: str) -> str:
    secret = os.environ.get("OPENAI_API_KEY", "")
    if secret and secret in text:
        text = text.replace(secret, "[REDACTED]")
    return text


_write_lock = threading.Lock()


def log_event(event: dict) -> None:
    TRACES_DIR.mkdir(exist_ok=True)
    event = dict(event)
    event.setdefault("ts", time.time())
    line = _redact(json.dumps(event, default=str))
    # One file per day; simple and greppable. Locked: evals run cases in
    # parallel threads sharing this file.
    path = TRACES_DIR / f"{time.strftime('%Y-%m-%d')}.jsonl"
    with _write_lock, path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def log_tool_call(name: str, arguments: dict, latency_ms: float, ok: bool, summary: str = "") -> None:
    log_event({
        "type": "tool_call",
        "tool": name,
        "arguments": arguments,
        "latency_ms": round(latency_ms, 1),
        "ok": ok,
        "result_summary": summary[:500],
    })


def check_no_secrets() -> list[str]:
    """Return trace files containing the raw API key (should be empty)."""
    secret = os.environ.get("OPENAI_API_KEY", "")
    leaked: list[str] = []
    if not secret:
        return leaked
    for path in TRACES_DIR.glob("*.jsonl"):
        if secret in path.read_text(encoding="utf-8", errors="ignore"):
            leaked.append(path.name)
    return leaked
