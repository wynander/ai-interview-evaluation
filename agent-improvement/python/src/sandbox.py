"""Sandboxed code/SQL execution for the agent — 0-1 BUILD.

The agent needs `run_python` (date math, deadline computation) and `run_sql`
(read-only lookups the typed tools don't cover). The starter has baseline
guards with real holes left for you:

  run_python: timeout + import allowlist + restricted builtins are in place;
    missing AST-level checks against obfuscation (getattr, split strings,
    dunder access) and resource limits.
  run_sql: parse gate (SELECT/WITH/EXPLAIN only) + timeouts + row caps are in
    place; still connects as SUPERUSER instead of the read-only role.

Candidate TODO — close the holes without breaking legit use:

  run_python:
    - Timeout (~2s) + block imports except {datetime, math, re, json}.
    - No file/network/builtin access (no open, exec, eval, __import__...).
    - Return value or stdout, truncated. Log to tool_audit_log.

  run_sql:
    - Use agent_database_url() (read-only role) — NEVER the superuser URL.
    - Parse-first: allow SELECT/WITH/EXPLAIN only; reject DROP/DELETE/UPDATE/
      INSERT/COPY/ALTER via sqlparse or a strict prefix check + deny-list.
    - Support dry_run=True: return EXPLAIN plan + estimated rows WITHOUT
      executing. Evals use this for red-team safety (plan is tested, DB is
      never touched by hostile statements).
    - Enforce LIMIT (default 50, max 200) + statement_timeout=5s.
    - Log every call to tool_audit_log.

Evals NEVER execute hostile SQL against your DB: red-team cases check that
dangerous statements are REJECTED at parse/plan stage and that row counts
are unchanged. See src/eval.py red-team section.
"""

from __future__ import annotations

import io
import multiprocessing as mp
import re

import psycopg
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from . import db
from .runtime_helpers import as_json

ALLOWED_IMPORTS = {"datetime", "math", "re", "json"}
BLOCKED_PATTERNS = [
    r"\bopen\s*\(", r"\bexec\s*\(", r"\beval\s*\(", r"__import__",
    r"\bos\b", r"\bsys\b", r"\bsubprocess\b", r"\bsocket\b",
]

# Restricted builtins: enough for date/math/string work, no I/O or introspection.
# Candidate TODO: add an AST precheck (reject dunder attribute access, getattr/
# globals()/locals() tricks) + CPU/memory limits, and add your own abuse tests.
import builtins as _builtins_module

_SAFE_BUILTIN_NAMES = {
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int",
    "len", "list", "max", "min", "print", "range", "round", "set",
    "sorted", "str", "sum", "tuple", "zip", "isinstance", "type",
}
_real_import = _builtins_module.__import__


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root not in ALLOWED_IMPORTS:
        raise ImportError(
            f"import of {name!r} blocked (allowlist: {sorted(ALLOWED_IMPORTS)})"
        )
    return _real_import(name, globals, locals, fromlist, level)


SAFE_BUILTINS = {name: getattr(_builtins_module, name) for name in _SAFE_BUILTIN_NAMES}
SAFE_BUILTINS["__import__"] = _safe_import

DENY_STATEMENTS = re.compile(
    r"\b(drop|delete|update|insert|alter|create|truncate|copy|grant|revoke|vacuum)\b",
    re.IGNORECASE,
)


def _exec_worker(code: str, queue: mp.Queue) -> None:
    """Worker for timeout support. Single namespace + restricted builtins.

    NOTE: exec() with SEPARATE globals/locals dicts breaks `def` bodies and
    comprehensions (they resolve via globals). A single namespace dict is the
    correct sandbox pattern — see DESIGN.md expectations.
    """
    buf = io.StringIO()
    try:
        namespace: dict = {"__builtins__": SAFE_BUILTINS}
        import contextlib
        with contextlib.redirect_stdout(buf):
            exec(code, namespace)
        result = namespace.get("result", buf.getvalue())
        queue.put({"ok": True, "result": str(result)[:2000]})
    except Exception as exc:  # noqa: BLE001
        queue.put({"ok": False, "result": f"{type(exc).__name__}: {exc}"})


class RunPythonInput(BaseModel):
    code: str = Field(description="Python snippet. Set `result = ...` or print(). Imports limited to datetime/math/re/json. 2s timeout.")


@tool("run_python", args_schema=RunPythonInput)
def run_python(code: str) -> str:
    """Run a small Python snippet for calculations (date math, deadlines).

    Sandboxed: 2s timeout, allowlisted imports (datetime/math/re/json), no
    FS/network/introspection. TODO (candidate): AST-level abuse checks,
    resource limits, and your own red-team tests in evals/custom_cases.py.
    """
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, code):
            return f"Blocked: code matches deny pattern {pattern}. Keep to datetime/math/re/json with no I/O."
    # Starter has a timeout via process join but still overly permissive exec.
    queue: mp.Queue = mp.Queue()
    proc = mp.Process(target=_exec_worker, args=(code, queue))
    proc.start()
    proc.join(timeout=2.0)
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return "Blocked: snippet timed out after 2s."
    if queue.empty():
        return "Snippet produced no output. Set `result = ...` or print()."
    outcome = queue.get()
    db.execute(
        "INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('run_python', %s)",
        (as_json({"code": code[:500]}),),
    )
    if outcome["ok"]:
        return as_json({"ok": True, "result": outcome["result"]})
    return f"Snippet failed: {outcome['result']}"


class RunSqlInput(BaseModel):
    query: str = Field(description="Read-only SELECT/WITH over orders/customers/etc. Writes are rejected; the documents table is not accessible here (use search_docs).")
    dry_run: bool = Field(default=False, description="If true, return EXPLAIN plan only without executing.")


def _is_readonly_query(query: str) -> tuple[bool, str]:
    text = query.strip().rstrip(";")
    if DENY_STATEMENTS.search(text):
        return False, "writes/DDL are not allowed (SELECT/WITH/EXPLAIN only)"
    first = text.split(None, 1)[0].upper() if text.split() else ""
    if first not in {"SELECT", "WITH", "EXPLAIN"}:
        return False, f"only SELECT/WITH/EXPLAIN allowed, got {first or '(empty)'}"
    return True, ""


@tool("run_sql", args_schema=RunSqlInput)
def run_sql(query: str, dry_run: bool = False) -> str:
    """Run a READ-ONLY SQL lookup (SELECT/WITH) or EXPLAIN plan.

    TODO (candidate): enforce read-only role + LIMIT + statement timeout.
    Starter flaw: uses the SUPERUSER url — switch to agent_database_url().
    """
    ok, reason = _is_readonly_query(query)
    if not ok:
        return f"Blocked: {reason}."

    # BAD (intentional): superuser URL. Candidate MUST switch to agent_database_url().
    url = db.database_url()
    try:
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SET statement_timeout = '5s'")
            if dry_run:
                cur.execute(f"EXPLAIN {query}" if not query.strip().upper().startswith("EXPLAIN") else query)
                plan = [dict(r) for r in cur.fetchall()]
                return as_json({"dry_run": True, "plan": plan})
            # TODO: enforce LIMIT if missing.
            cur.execute(query)
            rows = [dict(r) for r in cur.fetchmany(200)]
            db.execute(
                "INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('run_sql', %s)",
                (as_json({"query": query[:500]}),),
            )
            return as_json({"rows": rows, "truncated_at": 200})
    except Exception as exc:  # noqa: BLE001 — surfaced as actionable tool error
        return f"SQL failed: {exc}"


SANDBOX_TOOLS = [run_python, run_sql]
