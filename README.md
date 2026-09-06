# Clai

Clai is a canvas for designing physical products with AI. A draft produces one image and becomes a frozen result. Continue editing starts a new node from that image; the canvas is the edit history.

## Functionality

- Draft, running, result, and failed card states, enforced by API mutation guards.
- Continue editing to the right; Try another and Revise prompt below. Failed runs remain editable and retryable.
- Solid input-image wires and up to two dashed references, with numbered prompt chips.
- Area selection with brush, lasso, rectangle, and SAM click/text selection. Saving outlines the input and focuses the prompt; Run generates the change.
- FLUX Fill inpainting with a deterministic 3px composite seam. Pixels outside that band are preserved, and the result shows the preservation measurement.
- Durable database-backed runs with frozen requests, Celery transport, and first-party artifact ingestion.
- Nano Banana Pro generation and unmasked editing through fal.
- Canvas comparison of any two image nodes, full-size inspection, original downloads, and explicit editable chain collapse.
- Tripo 3D views with image colors and print, first-party GLB/preview storage, and textured replacement of older grey models. Hidden surfaces are inferred and fine details may vary.
- Draft conflict recovery across tabs, retained images after source deletion, automatic titles, canvas shortcuts, and project rename/delete.
- Read-only image selection for older multi-image nodes; new nodes make one image each.

References and area selections cannot be combined. Chain collapse supports plain instruction edits; it cannot replay selected regions or reference positions against another root. Unmasked preservation remains model-dependent. Auth and deployment are outside this implementation.

See the [lifecycle and migration notes](docs/node-lifecycle/README.md) and [30-second workflow capture](docs/node-lifecycle/workflow.webm). The capture uses a deterministic test provider.

## Stack

- Next.js, React, TypeScript, Tailwind CSS, and React Flow
- FastAPI, SQLAlchemy, and Alembic
- PostgreSQL, Redis, and Celery
- Docker Compose, npm, and uv

## Architecture

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

## Tests

```bash
make test
make test-postgres
make lint
npm --prefix frontend run build
npm --prefix frontend test
cd frontend && npx playwright test
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

The PostgreSQL suite uses a disposable test service and validates the version-mutation trigger, role/pin constraint, one-subject partial index, graph reset and subject-rename migrations, concurrent two-connect cap, and full fake-provider navy-shoe path. Automated tests never call fal.

The saved 100-pair regression corpus is local under `.data/drift-corpus`, with its index and per-operation baselines in `backend/tests/fixtures/drift-corpus-manifest.json`. Run the offline report without new generations:

```bash
backend/.venv/bin/python backend/scripts/report_drift_regression.py --observations .data/drift-corpus/metrics.json
```
