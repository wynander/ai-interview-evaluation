# Take-Home: Build a Trustworthy Support Agent (TypeScript track)

This is the TypeScript track. An equivalent Python track lives next to it
(`agent-improvement/python/`). Pick one and do it, not both.

You get a working-but-naive support agent: AI SDK tool-calling over
Postgres + external CRM/billing/incident services, ~3000 docs (30 real + generated
distractors), and an eval harness. Make it a product you'd trust: grounded,
safe, and robust at scale.

AI coding tools are explicitly allowed and expected. Hardcoding eval answers,
deleting distractor rows, or weakening eval checks is disqualifying — the
chaos suite reseeds with different data.

## What we assess

**Competent builder of AI products.** Not prompt trivia — judgment across the
AI stack: retrieval design, tool contracts, sandboxing, guardrails, evals, and
knowing what to leave unbuilt. We read your code, your evals, your
transcripts, and DESIGN.md.

The starter already passes most LLM cases. That is intentional — those are
regression floors, not the goal. Keep building until `make eval-dev` and
`make eval-chaos` are both green.

## Setup (do this first)

You need Docker + Compose and Node 20+. Our recommendation:

- **macOS**: [Docker Desktop](https://www.docker.com/products/docker-desktop/)
  (install, open it once, wait for the whale icon to stop animating).
  Lightweight alternative: `brew install colima docker docker-compose && colima start`.
- **Linux**: Docker Engine + Compose plugin via your distro packages.
- **Node**: `brew install node` or [nodejs.org](https://nodejs.org/) (want v20+;
  `npm` ships with it).

Verify before continuing:

```bash
docker compose version   # want Compose v2+
docker run --rm hello-world
node --version
```

No Docker trivia in this exercise — if `docker compose up` works, you're
done with infra. Everything else runs through the Makefile.

Then, from the repo root:

```bash
cd agent-improvement/typescript

# 1. Env file + API key. We sent you a gateway key with this exercise —
#    paste it into .env as OPENAI_API_KEY. (Model and gateway URL are
#    already wired in src/agent.ts; do not change them.)
cp .env.example .env
# now edit .env: OPENAI_API_KEY=<the key we sent you>

# 2. Start Postgres + the Next.js app in Docker.
docker compose up -d --build

# 3. Install deps and seed the database (~3k docs, ~15k orders).
npm install
make seed

# 4. Track your work in git from the start — we review history.
git init && git add -A && git commit -m "starter"
# then commit as you go
```

Sanity-check that everything works (no LLM calls, ~10 seconds):

```bash
npx tsx src/eval-retrieval.ts   # deterministic ranking probes
npx tsx src/eval.ts --static-only
```

Then open the chat UI at http://localhost:8001 and ask something, and run a
single LLM case end to end:

```bash
npx tsx src/eval.ts --cases refund --verbose
open eval-baseline.html   # per-case answers, traces, judge scores
```

If something breaks: `docker compose ps` / `docker compose logs web`
for service health, `make seed` to reseed from scratch, `docker compose up -d --build` to rebuild after touching the Dockerfile. Evals talk to the
compose services from your host, so keep the stack up while you work.

## The builds

### 1. Retrieval that works at scale (biggest)

Search must return the right official docs, with citations, at full corpus size.
Each case has a tool-call budget (4–10 depending on the expected path) — past
that the case fails fast. Deterministic probes (`npx tsx src/eval-retrieval.ts`) measure ranking directly.

### 2. Tools that handle messy services

The agent must stay correct when services are flaky, paginated, or
inconsistent — and keep every tool output canonical.

### 3. Sandboxed execution

`run_js` and `run_sql` must be safe to expose to the model without
breaking legitimate use. Red-team evals verify hostile statements never
execute and stored data never changes.

### 4. Guardrails

Tool output is untrusted data. The agent must not follow injected
instructions, must not leak internal-only material, and must handle
side effects responsibly.

### 5. Evals + own edge cases

Implement the judge, add 5+ cases for edges you found, and keep traces with
tool calls, latency, and cost. No secrets in traces.

### 6. Hygiene (small, do not skip)

The static checks define this track — make them pass.

## What you may change

Goal: make the evals, static checks, and probes pass by improving the system.
Read the checks to understand grading — then fix the code they exercise, not
the checks themselves.

| Area | Rule |
| --- | --- |
| Model + gateway (`OPENAI_MODEL`, `OPENAI_BASE_URL`, `temperature` in `src/agent.ts`) | **No.** Same model for everyone. |
| Seed data (`src/data.ts`, `src/db/seed.ts`, `src/db/generate-distractors.ts`) | **No.** Don't edit, weaken, or delete the corpus — grading runs reseed from these files. |
| Graded checks (`src/eval.ts` runner/checks, `src/eval-cases.ts` cases, `src/eval-retrieval.ts` probes, static checks, budgets) | **No.** Don't edit assertions, thresholds, or case budgets. |
| Agent + tools (`src/agent.ts`, `src/tools.ts`, `src/retrieval.ts`, `src/sandbox.ts`, `src/guardrails.ts`, `src/normalize.ts`, `src/tracing.ts`, `src/db.ts`) | **Yes — this is the work.** Restructure freely, but keep entry points working (`src/eval.ts`, `/api/chat`). |
| External services (`src/app/api/` routes, `src/lib/services-shared.ts`) | **Yes** — own it. Keep the routes and `SERVICES_API_URL` contract. |
| Chat page (`src/app/page.tsx`) | **Yes** — improve it if you want, but it isn't graded. |
| Schema (`src/db/migrations/`, `src/db/schema.ts`) | **Yes, additively.** Add numbered migrations (keep `src/db/schema.ts` in sync); don't rewrite `schema.sql` history. Grading replays your migrations onto a fresh seed. |
| Your own evals (`evals/judge.ts`, `evals/custom-cases.ts`) | **Yes — required.** Implement the judge, add 5+ cases for edges you found. |
| Docker (`.dockerignore`, `Dockerfile`) | **Yes** — own it. Don't redesign compose or services. |
| Dependencies (`package.json`) | **Yes** — add what you need via `npm`. |
| `DESIGN.md`, `traces/` | **Yes.** Keep secrets out of both. |

Anti-gaming (disqualifying): hardcoded answers keyed to eval questions,
special-casing eval entities, deleting or weakening seed rows or checks,
raising temperature to chase luck.

Reproducibility: grading unzips your submission and runs `docker compose up -d --build && make seed && make eval-dev && make eval-chaos`.
If it doesn't pass there, it doesn't pass.

## Scope discipline

- Don't redesign compose/networking, add streaming APIs, sagas, or queues.
  Docker is packaging, not the test.
- Don't micro-profile. Fix the big, obvious perf problems and move on.

## Submission Steps

1. `DESIGN.md` (template in repo): a brief overview of what you changed,
  key decisions and tradeoffs, and what still fails.
2. `eval-baseline.html` from your final runs — attach one from `make eval-dev`
  and one from `make eval-chaos` (rename the files so both are included).
3. Your AI session transcripts, in a `transcripts/` folder in this repo. How you work
  with AI tools is part of what we're assessing — export every session you used on this exercise, raw and unedited (JSONL is fine).
  - **Cursor**: right-click each chat tab → *Export Transcript* (saves `.md`).
  One file per session you used.
  - **Claude Code**: run `/export transcripts/<name>.txt` in each session,
  or copy the raw session files from
  `~/.claude/projects/<encoded-path>/<session-id>.jsonl`.
  - **Codex CLI**: copy the rollout files for your sessions from
  `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (match by date).
  - **Anything else** (Copilot, ChatGPT/Claude web, Aider, …): use whatever
  export/share-your-workflow your tool offers; raw logs or share links
  are both fine. When in doubt, over-include.
4. Your code as a zip of the repo root, including all of the above **plus
  the `.git` directory** Exclude secrets and junk:
  ```bash
  # from the repo root
  zip -r submission.zip . -x 'node_modules/*' '.next/*' '*.log' '.env' 'traces/*.jsonl'
  ```
  Do not open a branch or PR anywhere public. The zip (with `.git` inside) is the entire submission.
