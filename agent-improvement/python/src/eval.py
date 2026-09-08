"""Model-backed evaluations for multi-hop support tasks."""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from calendar import month_abbr, month_name
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .agent import AgentConfigurationError, AgentResult, AgentSession
from .runtime_helpers import reset_tickets, ticket_count

CASE_TIMEOUT_SECONDS = 120
HTML_REPORT_PATH = Path(__file__).resolve().parent.parent / "eval-baseline.html"


@dataclass(frozen=True)
class EvalCase:
    name: str
    turns: tuple[str, ...]
    expected_answer: str
    expected_why: str
    required_tools: tuple[str, ...] = ()
    response_fact_groups: tuple[tuple[str, ...], ...] = ()
    trace_fact_groups: tuple[tuple[str, ...], ...] = ()
    expected_ticket_delta: int | None = None
    require_related_order_id: str | None = None


@dataclass
class EvalOutcome:
    case: EvalCase
    passed: bool
    reason: str
    result: AgentResult
    turn_results: list[AgentResult] = field(default_factory=list)


@dataclass
class _CaseProgress:
    turn_results: list[AgentResult] = field(default_factory=list)
    ticket_delta: int = 0
    done: bool = False


CASES = [
    EvalCase(
        name="customer email lookup",
        turns=("What's the email on Maya Rodriguez's account?",),
        expected_answer="maya.rodriguez@example.test (customer C123).",
        expected_why="Baseline lookup: return the email on Maya Rodriguez's account.",
        response_fact_groups=(("maya.rodriguez@example.test",),),
        trace_fact_groups=(("C123",),),
    ),
    EvalCase(
        name="recent order history",
        turns=(
            "What were Maya Rodriguez's last two orders? Include order IDs and statuses.",
        ),
        expected_answer=(
            "O-1042 (delivered) and O-1031 (delivered) — the two most recent "
            "orders for C123."
        ),
        expected_why=(
            "Baseline history: report Maya's two most recent orders with IDs "
            "and statuses."
        ),
        response_fact_groups=(("O-1042",), ("O-1031",), ("delivered",)),
    ),
    EvalCase(
        name="account then renewal date",
        turns=(
            "Look up Alex Chen's account.",
            "When does that subscription renew?",
        ),
        expected_answer=(
            "December 15, 2026 (2026-12-15), based on commencement of the "
            "original Growth subscription order (O-2341, 2025-12-15)."
        ),
        expected_why=(
            "Renewal for Alex Chen's subscription. Subscription started_on is "
            "not the commencement date; conflicting renewal guidance exists in "
            "the documentation corpus."
        ),
        response_fact_groups=(("2026-12-15",),),
        trace_fact_groups=(
            ("C234",),
            ("SUB-234",),
            ("2025-12-15", "12/15/25"),
            ("term-anniversary", "commencement"),
        ),
    ),
    EvalCase(
        name="refund policy then order deadline",
        turns=(
            "What is the refund policy for annual plans?",
            "Apply that to Maya Rodriguez's Analytics Pro order. When does the window end?",
        ),
        expected_answer=(
            "Eighteen calendar days from order placed_on. For O-1042 "
            "(2026-08-14), the window ends 2026-09-01."
        ),
        expected_why=(
            "Apply the in-force annual-plan reversal window to Maya's Analytics "
            "Pro order. Documentation about refunds / money-back is inconsistent."
        ),
        response_fact_groups=(
            ("O-1042",),
            ("18", "eighteen"),
            ("2026-09-01",),
        ),
    ),
    EvalCase(
        name="delayed order context",
        turns=(
            "What should I tell the customer about order O-2014's delay, "
            "including any current service incident?",
        ),
        expected_answer=(
            "Order O-2014 for Jordan Kim (C456) is still processing. There is "
            "an active collaboration incident in Europe (Collaboration API "
            "processing delays) that explains the delay — describe it for the "
            "customer, not as an internal ID."
        ),
        expected_why=(
            "Customer-facing summary of O-2014's delay including any current "
            "service incident for Jordan Kim's product and region."
        ),
        response_fact_groups=(
            ("O-2014",),
            ("C456", "Jordan Kim"),
            (
                "Collaboration API processing delays",
                "processing delays",
                "taking longer than expected",
            ),
        ),
        trace_fact_groups=(("INC-204",),),
    ),
    EvalCase(
        name="ambiguous customer name",
        turns=("What plan is Alex on?",),
        expected_answer=(
            "Cannot answer without disambiguation — two matches: Alex Chen "
            "(C234, GRW) and Alexandra Chen (C235, STR). Both should appear."
        ),
        expected_why=(
            "'Alex' matches more than one customer. Answering for only one "
            "account is incorrect."
        ),
        response_fact_groups=(
            ("C234", "Alex Chen"),
            ("C235", "Alexandra"),
        ),
    ),
    EvalCase(
        name="existing migration ticket",
        turns=(
            "What open support ticket do we already have for Samira Patel's "
            "data migration package?",
        ),
        expected_answer=(
            "Ticket T-1001 for Samira Patel (C789) about the data migration "
            "package delivery window. Do not create a new ticket."
        ),
        expected_why=(
            "The user is asking what open ticket already exists — not to open "
            "a new one."
        ),
        response_fact_groups=(("T-1001",), ("C789", "Samira Patel")),
        trace_fact_groups=(("T-1001",),),
        expected_ticket_delta=0,
    ),
    EvalCase(
        name="ticket linked to delayed order",
        turns=(
            "Open a high-priority support ticket for the customer whose order "
            "O-2014 is delayed. Tie it to that order.",
        ),
        expected_answer=(
            "Create one high-priority ticket for Jordan Kim (C456) with "
            "related_order_id O-2014 persisted on the ticket record."
        ),
        expected_why=(
            "The user asks to open a high-priority ticket and tie it to order "
            "O-2014. Mentioning the order only in free-text issue notes is not "
            "enough — the ticket record must store the related order id."
        ),
        response_fact_groups=(("C456", "Jordan Kim"), ("high",), ("T-",)),
        expected_ticket_delta=1,
        require_related_order_id="O-2014",
    ),
    EvalCase(
        name="growth named user limit",
        turns=("How many named users does the Growth plan include?",),
        expected_answer="Twenty-two (22) named users for Growth.",
        expected_why=(
            "Growth named-user capacity. Documentation about Growth seats / "
            "named users is inconsistent."
        ),
        response_fact_groups=(("22", "twenty-two"),),
        trace_fact_groups=(("named-user-packaging",),),
    ),
    EvalCase(
        name="growth seat invoice timing",
        turns=(
            "When do added Growth seats show up on the invoice?",
        ),
        expected_answer=(
            "On the second subsequent invoice (not the next invoice)."
        ),
        expected_why=(
            "Billing timing for Growth seat changes. Documentation about when "
            "seat changes appear on invoices is inconsistent."
        ),
        response_fact_groups=(
            ("second subsequent", "second invoice", "two invoices"),
        ),
        trace_fact_groups=(("named-user-packaging",),),
    ),
    EvalCase(
        name="plan code to plan name",
        turns=(
            "Customer C123 is on plan code GRW — what's the commercial plan name?",
        ),
        expected_answer="Growth.",
        expected_why=(
            "Customer C123 stores plan code GRW. The commercial plan name is "
            "required, not the internal code alone."
        ),
        response_fact_groups=(("Growth",),),
        trace_fact_groups=(("plan-codes",), ("GRW",)),
    ),
    EvalCase(
        name="samira migration incident",
        turns=(
            "Is there an active service incident affecting Samira Patel's account? "
            "Summarize it for the customer.",
        ),
        expected_answer=(
            "Yes — an active migration incident in Asia Pacific about delivery "
            "window updates. Summarize for the customer."
        ),
        expected_why=(
            "Whether Samira Patel's account is affected by a current service "
            "incident, summarized for the customer."
        ),
        response_fact_groups=(
            ("C789", "Samira Patel"),
            (
                "Migration delivery window",
                "delivery window",
                "delivery windows",
            ),
        ),
        trace_fact_groups=(("INC-205",),),
    ),
    EvalCase(
        name="duplicate migration ticket",
        turns=(
            "Open a support ticket for Samira Patel about confirming the delivery "
            "window for her data migration package.",
        ),
        expected_answer=(
            "Do not create a new ticket — T-1001 already covers this for C789 "
            "and order O-3018. Point the user to the existing open ticket."
        ),
        expected_why=(
            "The user asks to open a ticket for an issue that already has an "
            "open ticket (T-1001). Creating another ticket is wrong."
        ),
        response_fact_groups=(("T-1001",), ("C789", "Samira Patel")),
        trace_fact_groups=(("T-1001",),),
        expected_ticket_delta=0,
    ),
    EvalCase(
        name="maya plan then seat limit",
        turns=(
            "Look up Maya Rodriguez's account.",
            "How many named users can she provision on that plan?",
        ),
        expected_answer=(
            "Twenty-two (22) named users on her Growth (GRW) plan."
        ),
        expected_why=(
            "Multi-turn: look up Maya's account, then answer named-user capacity "
            "for that plan. Seat / named-user documentation is inconsistent."
        ),
        response_fact_groups=(("22", "twenty-two"), ("GRW", "Growth")),
        trace_fact_groups=(("named-user-packaging",), ("C123",)),
    ),
    EvalCase(
        name="starter named user limit",
        turns=("How many named users does the Starter plan include?",),
        expected_answer="Eight (8) named users for Starter.",
        expected_why=(
            "Starter named-user capacity. Documentation about Starter seats / "
            "named users is inconsistent."
        ),
        response_fact_groups=(("8", "eight"),),
        trace_fact_groups=(("named-user-packaging",),),
    ),
    EvalCase(
        name="enterprise plan name",
        turns=(
            "What commercial plan is Samira Patel on? Give the plan name, not "
            "the internal code.",
        ),
        expected_answer="Enterprise.",
        expected_why=(
            "Samira Patel's account stores an internal plan code. The commercial "
            "plan name is required, not the code alone."
        ),
        response_fact_groups=(("Enterprise",),),
        trace_fact_groups=(("plan-codes",), ("ENT",)),
    ),
    EvalCase(
        name="processing investigation threshold",
        turns=(
            "Per our order policy, after how many business days in processing "
            "may support investigate the delay on order O-2014?",
        ),
        expected_answer=(
            "Five (5) business days in processing. Order O-2014 is still "
            "processing."
        ),
        expected_why=(
            "Order policy for how long an order may stay in processing before "
            "support may investigate, applied to O-2014."
        ),
        response_fact_groups=(
            ("O-2014",),
            ("5", "five"),
            ("business day", "business days"),
        ),
        trace_fact_groups=(("orders",),),
    ),
    EvalCase(
        name="jordan account then incident",
        turns=(
            "Look up Jordan Kim's account.",
            "Is there an active service incident for his product and region?",
        ),
        expected_answer=(
            "Yes — Collaboration API processing delays in Europe, affecting "
            "Jordan Kim's product and region."
        ),
        expected_why=(
            "Multi-turn: look up Jordan Kim's account, then say whether there "
            "is an active service incident for his product and region."
        ),
        response_fact_groups=(
            ("C456", "Jordan Kim"),
            (
                "Collaboration API processing delays",
                "processing delays",
                "taking longer than expected",
            ),
        ),
        trace_fact_groups=(("INC-204",),),
    ),
]


_MONTHS = {
    name.lower().rstrip("."): index
    for index, name in enumerate(month_name)
    if index
}
_MONTHS.update(
    {
        name.lower().rstrip("."): index
        for index, name in enumerate(month_abbr)
        if index
    }
)
_MONTHS["sept"] = 9
_MONTH_PATTERN = "|".join(
    sorted((re.escape(name) for name in _MONTHS), key=len, reverse=True)
)


def _full_year(year: int) -> int:
    if year < 100:
        return 2000 + year
    return year


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(_full_year(year), month, day)
    except ValueError:
        return None


def _dates_in(text: str) -> set[date]:
    found: set[date] = set()
    for match in re.finditer(r"\b(20\d{2}|19\d{2})-(\d{1,2})-(\d{1,2})\b", text):
        parsed = _date(int(match[1]), int(match[2]), int(match[3]))
        if parsed:
            found.add(parsed)
    for match in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text):
        parsed = _date(int(match[3]), int(match[1]), int(match[2]))
        if parsed:
            found.add(parsed)
    for match in re.finditer(
        rf"\b({_MONTH_PATTERN})\.? +(\d{{1,2}})(?:st|nd|rd|th)?,? +(\d{{2,4}})\b",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = _date(
            int(match[3]),
            _MONTHS[match[1].lower().rstrip(".")],
            int(match[2]),
        )
        if parsed:
            found.add(parsed)
    for match in re.finditer(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)? +({_MONTH_PATTERN})\.? +(\d{{2,4}})\b",
        text,
        flags=re.IGNORECASE,
    ):
        parsed = _date(
            int(match[3]),
            _MONTHS[match[2].lower().rstrip(".")],
            int(match[1]),
        )
        if parsed:
            found.add(parsed)
    return found


def _contains_fact(haystack: str, fact: str) -> bool:
    if fact.casefold() in haystack.casefold():
        return True
    expected = _dates_in(fact)
    return bool(expected) and bool(expected & _dates_in(haystack))


def _check_case(case: EvalCase, result: AgentResult, ticket_delta: int) -> str | None:
    if result.error:
        return result.error

    tool_names = {call.name for call in result.tool_calls}
    missing_tools = [
        name for name in case.required_tools if name not in tool_names
    ]
    if missing_tools:
        return f"missing required evidence tool(s): {', '.join(missing_tools)}"

    trace = "\n".join(
        f"{call.name} {call.arguments} {call.result or ''}"
        for call in result.tool_calls
    ).casefold()
    for group in case.trace_fact_groups:
        if not any(_contains_fact(trace, fact) for fact in group):
            return f"trace missing one of: {', '.join(group)}"

    response = result.response
    for group in case.response_fact_groups:
        if not any(_contains_fact(response, fact) for fact in group):
            return f"response missing one of: {', '.join(group)}"

    if (
        case.expected_ticket_delta is not None
        and ticket_delta != case.expected_ticket_delta
    ):
        return (
            f"expected ticket count change {case.expected_ticket_delta}, "
            f"got {ticket_delta}"
        )

    if case.require_related_order_id:
        linked = False
        for call in result.tool_calls:
            if call.name != "create_support_ticket" or not call.result:
                continue
            parsed = _parse_tool_result(call.result)
            if (
                isinstance(parsed, dict)
                and parsed.get("related_order_id") == case.require_related_order_id
            ):
                linked = True
                break
        if not linked:
            return (
                f"created ticket missing related_order_id "
                f"{case.require_related_order_id}"
            )

    return None


def _combine_turn_results(turn_results: list[AgentResult]) -> AgentResult:
    if not turn_results:
        return AgentResult(response="", error=None)

    last = turn_results[-1]
    return AgentResult(
        response=last.response,
        tool_calls=[
            record for result in turn_results for record in result.tool_calls
        ],
        error=last.error,
    )


def _timeout_outcome(case: EvalCase, progress: _CaseProgress) -> EvalOutcome:
    completed = len(progress.turn_results)
    total = len(_turns(case))
    if completed:
        reason = (
            f"timed out after {CASE_TIMEOUT_SECONDS}s "
            f"({completed}/{total} turn(s) completed)"
        )
    else:
        reason = f"timed out after {CASE_TIMEOUT_SECONDS}s"

    combined = _combine_turn_results(progress.turn_results)
    print(f"FAIL  {case.name}", flush=True)
    return EvalOutcome(
        case=case,
        passed=False,
        reason=reason,
        result=AgentResult(
            response=combined.response,
            tool_calls=combined.tool_calls,
            error=reason,
        ),
        turn_results=list(progress.turn_results),
    )


def _turns(case: EvalCase) -> tuple[str, ...]:
    turns = case.turns
    if isinstance(turns, str):
        return (turns,)
    return turns


def _execute_case(case: EvalCase, progress: _CaseProgress) -> EvalOutcome:
    reset_tickets()
    initial_ticket_count = ticket_count()
    session = AgentSession()
    for turn in _turns(case):
        turn_result = session.run(turn)
        progress.turn_results.append(turn_result)
        if turn_result.error:
            break

    progress.ticket_delta = ticket_count() - initial_ticket_count
    progress.done = True
    combined = _combine_turn_results(progress.turn_results)
    reason = _check_case(case, combined, progress.ticket_delta)
    return EvalOutcome(
        case=case,
        passed=reason is None,
        reason=reason or "all positive checks passed",
        result=combined,
        turn_results=list(progress.turn_results),
    )


def run_case(case: EvalCase) -> EvalOutcome:
    print(f"RUN   {case.name}", flush=True)
    progress = _CaseProgress()
    box: list[EvalOutcome] = []
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            box.append(_execute_case(case, progress))
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(CASE_TIMEOUT_SECONDS)
    if worker.is_alive():
        return _timeout_outcome(case, progress)
    if errors:
        raise errors[0]
    outcome = box[0]
    label = "PASS" if outcome.passed else "FAIL"
    print(f"{label}  {case.name}", flush=True)
    return outcome


def run_evaluation(cases: Iterable[EvalCase] = CASES) -> list[EvalOutcome]:
    case_list = list(cases)
    if not case_list:
        return []

    with ThreadPoolExecutor(max_workers=len(case_list)) as executor:
        return list(executor.map(run_case, case_list))


def _parse_tool_result(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def outcomes_to_report(outcomes: list[EvalOutcome]) -> dict[str, Any]:
    cases = []
    for outcome in outcomes:
        turns = []
        for index, turn_result in enumerate(outcome.turn_results):
            prompt = (
                _turns(outcome.case)[index]
                if index < len(_turns(outcome.case))
                else ""
            )
            turns.append(
                {
                    "input": prompt,
                    "response": turn_result.response,
                    "error": turn_result.error,
                    "tool_calls": [
                        {
                            "name": call.name,
                            "arguments": call.arguments,
                            "result": _parse_tool_result(call.result),
                        }
                        for call in turn_result.tool_calls
                    ],
                }
            )
        cases.append(
            {
                "name": outcome.case.name,
                "passed": outcome.passed,
                "reason": outcome.reason,
                "expected_answer": outcome.case.expected_answer,
                "expected_why": outcome.case.expected_why,
                "turns": turns,
            }
        )
    passed = sum(1 for outcome in outcomes if outcome.passed)
    return {"passed": passed, "total": len(outcomes), "cases": cases}


def write_html_report(outcomes: list[EvalOutcome]) -> None:
    payload = json.dumps(
        outcomes_to_report(outcomes),
        indent=2,
    ).replace("<", "\\u003c")
    html = HTML_REPORT_PATH.read_text(encoding="utf-8")
    start = '<script type="application/json" id="eval-data">'
    end = "</script>"
    start_at = html.find(start)
    end_at = html.find(end, start_at) if start_at != -1 else -1
    if start_at == -1 or end_at == -1:
        raise RuntimeError(
            f"{HTML_REPORT_PATH} is missing the eval-data script tag"
        )
    HTML_REPORT_PATH.write_text(
        html[: start_at + len(start)] + "\n" + payload + "\n    " + html[end_at:],
        encoding="utf-8",
    )


def _print_verbose(outcome: EvalOutcome) -> None:
    for index, turn_result in enumerate(outcome.turn_results, start=1):
        print(f"  turn {index}: {_turns(outcome.case)[index - 1]}")
        print(f"  response: {turn_result.response}")
        if turn_result.error:
            print(f"  error: {turn_result.error}")
        for call in turn_result.tool_calls:
            print(f"  tool: {call.name}({call.arguments})")
            if call.result is not None:
                print(f"  result: {call.result}")
    if not outcome.passed:
        print(f"  reason: {outcome.reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run support agent evaluations.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show responses, tool calls, and failure reasons.",
    )
    args = parser.parse_args()

    print("Agent Evaluation\n", flush=True)
    try:
        outcomes = run_evaluation()
    except AgentConfigurationError as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1

    passed = sum(1 for outcome in outcomes if outcome.passed)
    for outcome in outcomes:
        if args.verbose:
            print(f"\n{outcome.case.name}")
            _print_verbose(outcome)

    print(f"\n{passed} / {len(outcomes)} passed", flush=True)
    write_html_report(outcomes)
    print(f"Updated {HTML_REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
