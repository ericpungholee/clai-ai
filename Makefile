.PHONY: dev down logs migrate revision backend-shell db-shell test lint

dev:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose exec backend uv run alembic upgrade head

revision:
	docker compose exec backend uv run alembic revision --autogenerate -m "$(MSG)"

backend-shell:
	docker compose exec backend sh

db-shell:
	docker compose exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

test:
	docker compose exec frontend npm run lint
	docker compose exec frontend npm run typecheck

lint:
	docker compose exec backend uv run ruff check app alembic
	docker compose exec backend uv run ruff format --check app alembic
	docker compose exec frontend npm run lint
