.PHONY: dev down logs migrate revision backend-shell db-shell test test-postgres test-browser lint build

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
	docker compose run --rm backend uv run pytest -m "not postgres"
	docker compose run --rm --no-deps frontend npm test

test-postgres:
	docker compose --profile test run --rm backend-test

test-browser:
	npm --prefix frontend run test:browser

lint:
	docker compose run --rm --no-deps backend uv run ruff check app tests alembic
	docker compose run --rm --no-deps backend uv run ruff format --check app tests alembic
	docker compose run --rm --no-deps frontend npm run lint
	docker compose run --rm --no-deps frontend npm run typecheck

build:
	docker compose build
