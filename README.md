# Clai

Clai is a graph-based workspace for exploring product ideas.

## Current functionality

- Create and browse projects.
- Build project graphs on an infinite React Flow canvas.
- Create, move, connect, select, edit, and delete graph nodes and edges.
- Use prompt, image, and 3D node structures.
- Restore project graphs from PostgreSQL with debounced automatic saving.

## Stack

- Next.js, React, TypeScript, Tailwind CSS, and React Flow
- FastAPI, SQLAlchemy, and Alembic
- PostgreSQL, Redis, and Celery
- Docker Compose, npm, and uv

## Architecture

Next.js server components load projects and graph documents from FastAPI. React
Flow owns immediate client-side graph interaction, then sends debounced document
updates through FastAPI. FastAPI validates and synchronizes nodes and edges in a
single PostgreSQL transaction. Nodes and edges use separate tables, with JSONB
reserved for node-specific data.

```text
Next.js and React Flow → FastAPI → PostgreSQL
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
