# Clai

Clai is a node-based canvas for concepting physical products with AI. Wiring an immutable image version into another node as its base changes the next run from generation to an identity-preserving edit.

## P0 functionality

- Unified design nodes with prompts, active artifacts, pinned-base thumbnails, version strips, and pre-run operation chips.
- Base wires pin a specific immutable version. A second base wire replaces the first atomically.
- Branch creation from any historical version.
- Pure input resolution, operation routing, preservation-prompt construction, seed inheritance, and request freezing before enqueue.
- Durable database-backed run jobs transported by Celery.
- Nano Banana Pro generation/edit dispatch through fal, followed by first-party artifact ingestion.
- Insert-only versions with provenance and internal per-operation DINOv2 change telemetry.

## Stack

- Next.js, React, TypeScript, Tailwind CSS, and React Flow
- FastAPI, SQLAlchemy, and Alembic
- PostgreSQL, Redis, and Celery
- Docker Compose, npm, and uv

## Architecture

React Flow owns immediate pan, zoom, selection, and drag state. Scoped FastAPI mutations persist nodes and pinned base edges without rewriting the graph. Run submission resolves and freezes the graph synchronously into `run_jobs`; workers dispatch only that frozen request and never re-resolve live wiring. Provider output is copied into Clai storage before a transaction appends the version and advances the node's active version.

```text
React Flow → scoped FastAPI mutations → PostgreSQL
                         ↓
                 frozen run_jobs → Celery → fal → Clai artifact storage
```

## Local development

Requirements:

- Docker with Compose v2
- Node.js 22+, Python 3.12+, and [uv](https://docs.astral.sh/uv/) for
  development outside Docker

Create the local environment file and set `POSTGRES_PASSWORD`:

```bash
cp .env.example .env
```

```bash
make dev
make migrate
```

Open:

- App: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Tests

```bash
make test
make test-postgres
make lint
npm --prefix frontend run build
```

Useful development commands:

```bash
make dev
make down
make logs
make migrate
make revision MSG="describe change"
make backend-shell
make db-shell
```

`GET /health` checks the API process. `GET /health/ready` verifies PostgreSQL
and Redis connectivity. PostgreSQL data persists across `make down`.

The PostgreSQL suite uses a disposable test service and validates the version-mutation trigger, role/pin constraint, one-base partial index, graph reset migration, concurrent two-connect cap, and full fake-provider navy-shoe path. Automated tests never call fal.
