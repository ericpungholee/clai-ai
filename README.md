# Clai

Clai is a canvas for designing physical products with AI. A draft produces one image and becomes a frozen result. Continue editing starts a new node from that image; the canvas is the edit history.

## Functionality

- Draft, running, result, and failed card states, enforced by API mutation guards.
- Continue editing creates a new draft to the right. Failed runs remain editable and retryable.
- Solid input-image wires and up to two dashed references, with numbered prompt chips.
- Area selection with brush, lasso, rectangle, and SAM click/text selection. Saving outlines the input and focuses the prompt; Run generates the change.
- FLUX Fill inpainting with a deterministic 3px composite seam. Pixels outside that band are preserved.
- Durable database-backed runs with frozen requests, Celery transport, and first-party artifact ingestion.
- Nano Banana Pro generation and unmasked editing through fal.
- Canvas comparison of any two image nodes, full-size inspection, original downloads, and explicit editable chain collapse.
- Tripo 3D views with full 360° rotation, image colors and print, source-logo placement, first-party GLB/preview storage, GLB exports, and textured replacement of older grey models. Hidden surfaces are inferred and fine details may vary.
- Draft conflict recovery across tabs, retained images after source deletion, optional node names, canvas shortcuts, and project rename/delete.
- Read-only image selection for older multi-image nodes; new nodes make one image each.

References and area selections cannot be combined. Chain collapse supports plain instruction edits; it cannot replay selected regions or reference positions against another root. Unmasked preservation remains model-dependent. Auth and deployment are outside this implementation.

## Stack

- Next.js, React, TypeScript, Tailwind CSS, and React Flow
- FastAPI, SQLAlchemy, and Alembic
- PostgreSQL, Redis, and Celery
- Docker Compose, npm, and uv

## Architecture

See [architecture.md](architecture.md) for the code-level system guide, data model, save/conflict behavior, provider pipelines, storage, and operational limits.

React Flow owns immediate pan, zoom, selection, and drag state. Scoped FastAPI mutations persist editable drafts and input wires. Run submission resolves and freezes inputs synchronously into `run_jobs`; workers dispatch that frozen request. Provider output is copied into Clai storage before a transaction records the node's image. Successful nodes reject changes to generation inputs and cannot run again.

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

Set `FAL_KEY` to enable generation, SAM selection and 3D. Artifacts default to a shared local volume; both the API and worker must use the same storage. Provider outputs are copied there before committing a version or mesh cache.

The frontend installs locked dependencies into its Docker volume before starting Next.js. Its build cache also uses a dedicated volume so Docker and local builds do not overwrite each other.

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

## Validation

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
