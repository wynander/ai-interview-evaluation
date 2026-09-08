# Applied AI Interview: Agent Improvement

You receive a small fictional customer-support agent with local synthetic data, tools, and an
evaluation harness. Inspect it, run it, find where it breaks, and improve it.
Cursor, Claude Code, Codex, and other AI coding tools are explicitly allowed.

The agent uses LangChain tool-calling. The interactive CLI and programmatic
`AgentSession` share the same implementation. The eval harness runs 18
scenarios concurrently and checks responses, tool traces, and ticket state.

## What we assess

We care about **judgment across the AI stack**, not just prompt tweaks —
retrieval, tool design, agent loop behavior, state handling, and identity /
ambiguity. The starter agent is intentionally weak (~40% on the baseline
eval). A perfect score is not expected in 30 minutes.

## Model access

The interviewer provides a short-lived Vercel AI Gateway API key. Put it in
`agent-improvement/python/.env` as `OPENAI_API_KEY`. The gateway URL and model
are hardcoded in `src/agent.py`; do not add other model configuration.

## Interview flow

| Approx. time | Activity |
| --- | --- |
| ~5 min | Read this README, skim the code, open `eval-baseline.html` |
| ~30 min | Improve the agent (any layer except `src/data.py`) |
| ~10 min | Discuss what you changed and what you would do next |

## Start here

```bash
cd agent-improvement/python
uv sync
cp .env.example .env
# Add the provided OPENAI_API_KEY to .env
```

**Review the baseline before running eval:**

Open `agent-improvement/python/eval-baseline.html` in a browser. Each case
shows the expected answer, why the case exists, failure reasons, and full tool
traces.

**Try the agent interactively:**

```bash
uv run python -m src.main
```

**Re-run eval after changes:**

```bash
uv run python -m src.eval
uv run python -m src.eval --verbose   # print traces to the terminal
```

Each eval run overwrites `eval-baseline.html`. Cases run concurrently with a
2-minute timeout per case.

## What you may change

| OK to edit | Leave alone |
| --- | --- |
| `src/agent.py` — system prompt, model wiring, loop behavior | `src/data.py` — synthetic corpus and records |
| `src/tools.py` — tool schemas, retrieval, normalization | |
| `src/runtime_helpers.py` — shared runtime utilities | |
| `src/eval.py` — only if you want to add cases while developing | |

Do not delete untrusted or archived documentation rows from `data.py`. Fixes
should handle bad retrieval in the agent layer.

See `python/README.md` for project layout and tool inventory.
