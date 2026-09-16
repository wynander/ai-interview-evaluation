# Support Agent — Take-Home v2

A LangChain support agent over Postgres + mock services. The starter **works
but is naive**: full-scan retrieval, page-1-only API clients, unsafe code/SQL
execution, no guardrails, substring-only evals. Your job is the **0-1 build**:
make it grounded, safe, and robust at scale.

AI coding tools (Cursor, Claude Code, Codex, etc.) are explicitly allowed.

## Prerequisites

You need Docker + Compose and `uv`. Our recommendation:

- **macOS**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  (simplest — install, open it once, wait for the whale icon to stop animating).
  Lightweight alternative: `brew install colima docker docker-compose && colima start`.
- **Linux**: Docker Engine + Compose plugin via your distro packages.
- **`uv`**: `curl -LsSf astral.sh/uv/install.sh | sh` (or `brew install uv`).

Verify before continuing:

```bash
docker compose version   # want Compose v2+
docker run --rm hello-world
uv --version
```

No Docker trivia in this exercise — if `docker compose up` works, you're done
with infra. Everything else runs through the Makefile below.

## Setup

```bash
cd agent-improvement/python
cp .env.example .env
# Add the provided OPENAI_API_KEY to .env
docker compose up -d --build
uv sync
make seed
```

`make seed` loads canonical rows + ~3000 generated distractor docs + a 15k-order
load-test customer. Safe to re-run. Grading reseeds with a different
seed, so don't hardcode doc IDs or counts.

## Run

```bash
# Interactive CLI (host, talks to compose services)
uv run python -m src.main

# Mock APIs directly
open http://localhost:8001/health

# Postgres
make psql
```

## Evaluate

```bash
make eval-dev              # probes + statics + LLM cases (two-phase: parallel, then isolated)
uv run python -m src.eval --cases refund --verbose   # iterate on one case
uv run python -m src.eval --static-only              # no LLM: leak + latency + audit checks
uv run python -m src.eval_retrieval                  # no LLM: deterministic ranking probes
make eval-chaos            # resilience check (reseed + CHAOS=1 flaky services)
```

Open `eval-baseline.html` after a run for per-case expected answers, traces,
and judge scores. Each eval run overwrites it.

## What to build

Start with INSTRUCTIONS.md — it defines the six builds, what you may change,
and what to submit. This README is the command reference; the project layout
below shows where each build lives.

## Project layout

```text
compose.yml            db + mock-apis + app (packaging, not the test)
Dockerfile             see static checks before shipping
Makefile               up / seed / eval-dev / eval-chaos / psql / logs
db/
  schema.sql           naive starter schema (TEXT dates, no indexes/FKs)
  migrations/          YOUR migrations go here (numbered .sql)
scripts/
  generate_distractors.py  deterministic distractor docs (seedable)
  seed.py              truncate + reseed + apply migrations
mock_apis/main.py      flawed CRM/billing/incident services (fix client + server)
src/
  agent.py             LangChain agent + system prompt + guardrail wiring
  tools.py             tool contracts (DB + mock APIs) with TODOs
  retrieval.py         YOUR main build: ingestion + search + citations
  sandbox.py           YOUR build: safe run_python / run_sql
  guardrails.py        YOUR build: injection + internal + confirmation checks
  normalize.py         ID/date normalization helpers
  tracing.py           JSONL traces + secret scan
  db.py                pooling + read/write URL helpers
  eval.py              24 dev cases + static checks + HTML report
evals/
  judge.py             YOUR build: LLM-as-judge quality signal (non-gating)
  custom_cases.example.py  copy to custom_cases.py, add 5+ own cases
traces/                JSONL run logs (never commit secrets)
DESIGN.md              YOUR writeup (template in repo)
eval-baseline.html     regenerated report
```

## Services & env

| Var | Default (host) | In compose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://agent:agentdev@localhost:5432/support` | `...@db:5432/...` |
| `AGENT_DATABASE_URL` | `postgresql://agent_readonly:...@localhost...` | `...@db...` (read-only role, for `run_sql` only) |
| `MOCK_API_URL` | `http://localhost:8001` | `http://mock-apis:8001` |
| `MOCK_API_KEY` | `dev-insecure-key` | same (fix auth; don't ship default) |

Model and gateway URL are fixed in `src/agent.py`. Do not add other models.
