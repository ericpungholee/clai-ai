# Clai

Clai is a node-based canvas for concepting physical products with AI. Wiring an immutable image version into another node as its subject changes the next run from generation to a subject-based edit.

## Functionality

- Unified design nodes with prompts, active artifacts, subject thumbnails, and version strips.
- Subject wires pin a specific immutable version. A second subject wire replaces the first atomically.
- Branch creation from any historical version.
- Pure input resolution, operation routing, preservation-prompt construction, seed inheritance, and request freezing before enqueue.
- Durable database-backed run jobs transported by Celery.
- Nano Banana Pro generation/edit dispatch through fal, followed by first-party artifact ingestion.
- Insert-only versions with provenance and internal per-operation DINOv2 change telemetry.
- Subject-version-bound masks with brush, lasso, rectangle and SAM click/text selection.
- FLUX Fill inpainting followed by a deterministic 3px composite seam; pixels outside that band are preserved from the original. Full-image selections become ordinary edits, and stale masks block runs.
- Atomic connect chips/wires, following active source images in sentence order, with a two-connect cap and broken-source blocking.
- Full-size image inspection, original download, side-by-side comparison, retained hidden versions, branch navigation and explicit editable chain collapse.
- Version-specific Tripo 3D form view, default grey geometry ($0.20), optional standard textures ($0.30), first-party GLB/preview storage, and explicit occlusion warnings.
- Durable run progress across reloads, draft conflict handling across tabs, node duplication, canvas shortcuts and project rename/delete with retained history.

Limits: FLUX Fill cannot accept connect images, so mask + connect runs are explicitly blocked. Chain collapse supports plain instruction edits; it cannot safely replay masks or reference-image positions against a different root. Unmasked preservation is model-dependent, not a pixel guarantee. The Tripo contract check succeeded in about 72 seconds through upload and provider response, before download; queue time and textures may take longer. Auth and deployment are out of scope.

## Stack

- Next.js, React, TypeScript, Tailwind CSS, and React Flow
- FastAPI, SQLAlchemy, and Alembic
- PostgreSQL, Redis, and Celery
- Docker Compose, npm, and uv

## Architecture

React Flow owns immediate pan, zoom, selection, and drag state. Scoped FastAPI mutations persist nodes and pinned subject edges without rewriting the graph. Run submission resolves and freezes the graph synchronously into `run_jobs`; workers dispatch only that frozen request and never re-resolve live wiring. Provider output is copied into Clai storage before a transaction appends the version and advances the node's active version.

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
