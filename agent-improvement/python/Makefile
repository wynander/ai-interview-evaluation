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
	uv run python -m scripts.seed --distractors 3000
	@echo "Seeded. Row counts:"
	@uv run python -m scripts.seed --counts-only

# Public dev evals: functional + perf + safe red-team. Never mutates seed data.
eval-dev:
	uv run python -m src.eval

eval-dev-verbose:
	uv run python -m src.eval --verbose

# Resilience check: same suite, reseeded distractors + flaky services.
eval-chaos:
	uv run python -m scripts.seed --distractors 3000 --seed 999
	CHAOS=1 uv run python -m src.eval
	uv run python -m scripts.seed --distractors 3000 --seed 42

logs:
	docker compose logs --tail=200 -f

psql:
	docker compose exec db psql -U agent -d support

reset:
	docker compose down -v
	docker compose up -d --build

traces-clean:
	rm -f traces/*.jsonl
