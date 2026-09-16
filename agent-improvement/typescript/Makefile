.PHONY: up down seed eval-dev eval-chaos logs psql reset traces-clean

# One-command sandbox. No Docker trivia — this should just work.
up:
	docker compose up -d --build
	@echo "Waiting for services to be healthy..."
	@sleep 3
	@docker compose ps

down:
	docker compose down

# Seed Postgres (canonical docs + generated distractors + customers/orders).
# Safe to re-run: truncates and re-seeds inside a transaction.
seed:
	npx tsx src/db/seed.ts --distractors 3000
	@echo "Seeded. Row counts:"
	@npx tsx src/db/seed.ts --counts-only

# Public dev evals: functional + perf + safe red-team. Never mutates seed data.
eval-dev:
	npx tsx src/eval.ts

eval-dev-verbose:
	npx tsx src/eval.ts --verbose

# Resilience check: same suite, reseeded distractors + flaky services.
eval-chaos:
	npx tsx src/db/seed.ts --distractors 3000 --seed 999
	CHAOS=1 npx tsx src/eval.ts
	npx tsx src/db/seed.ts --distractors 3000 --seed 42

logs:
	docker compose logs --tail=200 -f

psql:
	docker compose exec db psql -U agent -d support

reset:
	docker compose down -v
	docker compose up -d --build

traces-clean:
	rm -f traces/*.jsonl
