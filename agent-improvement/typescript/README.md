# Support Agent — Take-Home v2 (TypeScript track)

An AI SDK support agent over Postgres + external services, with a chat UI. The
starter **works but is naive**: full-scan retrieval, page-1-only API clients,
unsafe code/SQL execution, no guardrails, substring-only evals. Your job is
the **0-1 build**: make it grounded, safe, and robust at scale.

AI coding tools (Cursor, Claude Code, Codex, etc.) are explicitly allowed.

## Prerequisites

You need Docker + Compose and Node 20+. Our recommendation:

- **macOS**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  (simplest — install, open it once, wait for the whale icon to stop animating).
  Lightweight alternative: `brew install colima docker docker-compose && colima start`.
- **Linux**: Docker Engine + Compose plugin via your distro packages.
- **Node**: `brew install node` or [nodejs.org](https://nodejs.org/) (want v20+).

Verify before continuing:

```bash
docker compose version   # want Compose v2+
docker run --rm hello-world
node --version
```

No Docker trivia in this exercise — if `docker compose up` works, you're done
with infra. Everything else runs through the Makefile below.

## Setup

```bash
cd agent-improvement/typescript
cp .env.example .env
# Add the provided OPENAI_API_KEY to .env
docker compose up -d --build
npm install
make seed
```

`make seed` loads canonical rows + ~3000 generated distractor docs + a 15k-order
load-test customer. Safe to re-run. Grading reseeds with a different
seed, so don't hardcode doc IDs or counts.

## Run

```bash
# Chat UI (same agent core as the evals) + external APIs, served by Next.js
open http://localhost:8001
open http://localhost:8001/api/health

# Postgres
make psql
```

## Evaluate

```bash
make eval-dev              # probes + statics + LLM cases (two-phase: parallel, then isolated)
npx tsx src/eval.ts --cases refund --verbose   # iterate on one case
npx tsx src/eval.ts --static-only              # no LLM: leak + latency + audit checks
npx tsx src/eval-retrieval.ts                  # no LLM: deterministic ranking probes
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
compose.yml            db + web (packaging, not the test)
Dockerfile             see static checks before shipping
Makefile               up / seed / eval-dev / eval-chaos / psql / logs
src/
  app/
    page.tsx           chat UI (same agent core as evals; not graded)
    api/chat/route.ts  chat turn endpoint (uses src/agent.ts)
    api/*/route.ts     flawed CRM/billing/incident services (fix client + server)
  lib/
    services-shared.ts services auth/chaos/aliases helpers
  db/
    schema.sql         naive starter schema (TEXT dates, no indexes/FKs)
    schema.ts          drizzle view of the schema (keep in sync with migrations)
    migrations/        YOUR migrations go here (numbered .sql)
    seed.ts            truncate + reseed + apply migrations
    generate-distractors.ts  deterministic distractor docs (seedable)
  agent.ts             AI SDK agent + system prompt + guardrail wiring
  tools.ts             tool contracts (DB + external services) with TODOs
  retrieval.ts         YOUR main build: ingestion + search + citations
  sandbox.ts           YOUR build: safe run_js / run_sql
  guardrails.ts        YOUR build: injection + internal + confirmation checks
  normalize.ts         ID/date normalization helpers
  tracing.ts           JSONL traces + secret scan
  db.ts                drizzle clients + pooling + read/write URL helpers
  data.ts              canonical seed data (DO NOT MODIFY)
  eval.ts              31 cases + static checks + HTML report
  eval-retrieval.ts    deterministic ranking probes (no LLM)
evals/
  judge.ts             YOUR build: LLM-as-judge quality signal (non-gating)
  custom-cases.example.ts  copy to custom-cases.ts, add 5+ own cases
traces/                JSONL run logs (never commit secrets)
DESIGN.md              YOUR writeup (template in repo)
eval-baseline.html     regenerated report
```

## Services & env

| Var | Default (host) | In compose |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://agent:agentdev@localhost:5432/support` | `...@db:5432/...` |
| `AGENT_DATABASE_URL` | `postgresql://agent_readonly:...@localhost...` | `...@db...` (read-only role, for `run_sql` only) |
| `SERVICES_API_URL` | `http://localhost:8001` | `http://localhost:8001` (same Next.js app) |
| `SERVICES_API_KEY` | `dev-insecure-key` | same (fix auth; don't ship default) |

Model and gateway URL are fixed in `src/agent.ts`. Do not add other models.
