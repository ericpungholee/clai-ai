# Clai architecture refactor plan

Status: Phase 0 audit approved and P0-zero spike completed on 2026-09-03. Production P0 has not started; it is blocked pending acceptance of the spike report and its prompt-builder amendment.

Audit basis: `main` at `a8dd694` on 2026-09-03. The worktree was clean before this report. The inventory below classifies all 69 tracked files plus the ignored project report at `.progress/current.md`. Local secrets (`.env`) and generated/vendor directories (`.git`, `.next`, `node_modules`, `.venv`, pytest/ruff caches, and TypeScript build output) are intentionally excluded. `REFACTOR_PLAN.md` itself did not exist at audit start and is not classified.

No production code has been changed.

## Existing architecture map

### Data and persistence

- `projects` is the only product-level aggregate. It has UUID identity, name, timestamps, and an unused `thumbnail_url`.
- `graph_nodes` stores `prompt`, `image`, or `model3d` nodes with position and untyped JSONB `data`.
- `graph_edges` stores generic source/target handles. It has no role, pin, ordering, or cardinality rules.
- A composite foreign-key design prevents cross-project edges and cascades edge deletion when a node is deleted.
- There are no versions, masks, artifacts, run records, provider jobs, drift metrics, meshes, users, organizations, billing records, or storage records.
- PostgreSQL is the production database. Tests substitute SQLite in memory, so PostgreSQL-only constraints and triggers are not currently exercised.

### API surface

- `GET /health` checks the API process; `GET /health/ready` checks PostgreSQL and Redis.
- `GET/POST /api/projects` and `GET /api/projects/{id}` provide project list/create/read only.
- `GET /api/projects/{id}/graph` returns the full graph.
- `PUT /api/projects/{id}/graph` deletes every edge, deletes omitted nodes, mutates existing nodes, and recreates edges in one transaction.
- The graph PUT validates unique IDs, finite positions, known node types, local endpoints, and cross-project ownership. It has last-write-wins semantics and no optimistic concurrency control.
- There are no run, version, branch, mask, upload, artifact, job-status, webhook, cost, or deletion-refcount APIs.

### Run/generation pipeline

- No generation pipeline exists. There is no resolution, operation classification, prompt builder, provider-neutral request, dispatch, commit, or scoring layer.
- `backend/app/services/` is empty.
- Celery and Redis are wired, but the only task is `clai.ping`; there is no durable run/job state, retry policy, idempotency key, provider request ID, webhook handler, or reconciliation path.

### Canvas state and UI

- React Flow owns immediate node/edge state, selection, dragging, connection, deletion, pan, and zoom.
- Nodes and edges are loaded server-side, converted to React Flow types, then autosaved as a full graph document 700 ms after a mutation.
- Pan/zoom works but viewport state is not persisted.
- Prompt nodes have a textarea. Image and 3D nodes are placeholders with no artifact contract.
- Edges are generic. There is no base/connect distinction, version pin, active-version following, chip editor, resolved-op preview, version strip, branching marker, mask editor, or broken-reference state.

### Provider integrations

- None exist. No fal, BFL, OpenAI, SAM, embedding, or Meshy SDK/client is installed or configured.
- Provider secrets are absent from `.env.example` and the runtime settings model.

### Storage/CDN, auth, and billing

- Object storage/CDN wiring does not exist. Provider URLs would currently be the only possible artifact URLs, and some provider result URLs are explicitly temporary.
- Auth and tenant isolation do not exist; every project is globally visible.
- Billing and cost metering do not exist.
- Therefore the instruction to preserve auth, storage/CDN, and billing cannot literally be satisfied. They must either be supplied from another branch/system or treated as new prerequisites. The only orthogonal systems that actually exist to preserve are React Flow canvas interaction and the Redis/Celery skeleton.

## Target shape

### Persistence boundaries

Keep `Project` as the current canvas aggregate and interpret the brief's `canvasId` as the existing `project_id`. Do not introduce a second `Canvas` table unless the product needs multiple canvases per project.

Replace the generic persisted graph shape with normalized records:

- `graph_nodes`: one runnable image-concept node type, with `project_id`, title, prompt, settings, optional seed, optional canonical mask payload and mask base-version ID, active-version ID, position, timestamps, and a soft-delete marker if broken references must remain representable.
- `graph_edges`: source/target node IDs, role, pin mode, nullable pinned version ID, and nullable connect order. Add role/pin check constraints, a partial unique index for one base edge per target, and transactional/locking enforcement for at most two connect edges. Connect orders must be unique per target and normalized to `0..n-1`.
- `versions`: insert-only generation facts and provenance. Store artifact identity/URL, operation, provider, exact model/endpoint identifier, params, seed, input snapshot, runtime prompt, and edit depth. Reject updates and deletes at the database boundary.
- `version_metrics`: one-to-one mutable derived score/status keyed by version.
- `version_meshes`: one-to-one mutable derived cache keyed by version.
- `run_jobs`: durable async state, resolved request snapshot, provider request ID, attempts, errors, timestamps, and an idempotency key. Celery is transport, not the source of job truth.

The graph read API may aggregate these tables into the client document, but graph editing must not be able to write version rows.

### API boundaries

- Retain a graph read endpoint for initial hydration.
- Replace full-document destructive writes with scoped node mutation and edge mutation endpoints. Position/prompt/title/settings/seed/mask/active-version changes remain mutable; versions use create/read only.
- Make base-edge replacement one server transaction. Enforce both edge caps in the API and database-safe transaction path so two concurrent requests cannot exceed them.
- Add a run-preview response that returns the canonical resolved operation and stale/broken-input errors. Mirror the six-row pure classifier in TypeScript for instant UI updates and parity-test it against the backend table.
- `POST .../nodes/{node_id}/runs` resolves, classifies, and builds synchronously from one database snapshot, persists the frozen run request, and then enqueues it. The worker dispatches only that frozen request; it never resolves the live graph again.
- Commit a version and advance `activeVersionId` in one transaction after the artifact has been copied into durable Clai-controlled storage.
- Keep provenance read-only at generation time. A rerun is a new run reconstructed explicitly from a chosen historical snapshot, never implicit prompt inheritance.

### Pure run core

Create pure, network-free modules for:

1. Resolution: resolve the base pin, ordered connect pins, mask validity, and seed from an immutable input graph snapshot.
2. Classification: cover all six valid rows and reject invalid states such as a mask without a base or more than two connects.
3. Prompt construction: add the preservation preamble only for edit operations, replace atomic chip tokens with positional image references, and return the exact runtime prompt.

Network/storage/queue calls stay behind dispatch and commit interfaces. Tests use fixed clocks, IDs, and random-seed sources.

### Providers and artifacts

- Use separate adapters for Nano Banana Pro, FLUX Fill, SAM 3 RLE, GPT Image 2 fallback/composite, drift scoring, and Meshy. Each adapter declares capabilities and converts the provider-neutral request without silently dropping fields.
- Use `fal-ai/nano-banana-pro` for text-to-image and `fal-ai/nano-banana-pro/edit` when one or more input images exist. They are the same model family but different API contracts.
- Use `fal-ai/flux-pro/v1/fill` for single-base masked inpainting while it remains available.
- Use `fal-ai/sam-3/image-rle` when the stored result must be RLE. The `fal-ai/sam-3/image` endpoint returns mask image files, not the canonical RLE field.
- Ingest every successful provider result into durable first-party object storage before committing a version. Never persist a temporary fal/BFL/Meshy result URL as `artifactUrl` or `MeshRef`.
- Treat capability-based routing as explicit configuration with tests. A required mask or reference count that no configured provider can honor is a visible run error.

## Resolved conflicts and gate decisions

The audit gates below were decided in the approved P0 implementation brief. That brief supersedes `CLAI_REFACTOR_PROMPT.md` where they conflict.

1. **Version immutability conflicts with later patching.** The brief says versions are never updated, then says to patch `driftScore` and attach `mesh` later. Recommendation: make the `versions` row strictly immutable and put asynchronous metrics and mesh cache records in separate one-to-one tables. The API can still serialize them as fields on `Version`.

2. **Role/pin semantics are contradictory.** “Base edges pin; connect edges follow active” implies only `(base, version)` and `(connect, active)` are valid, while the `Pin` union and “default” wording imply all four combinations might be allowed. Resolution pseudocode also ignores a version-pinned connect. Recommendation: enforce the two invariant combinations in v1 and loosen the schema later only with a concrete UX.

3. **FLUX Fill cannot implement `edit_composite` as specified.** Its documented fal input is one `image_url`, one `mask_url`, and prompt; there is no reference-image list. Decision: keep FLUX Fill for `edit_inpaint`; defer the entire `edit_composite` operation and GPT Image 2 adapter to P2 so neither influences P0 or P1.

4. **A provider mask is not a hard pixel guarantee.** OpenAI explicitly documents GPT Image masking as prompt-based guidance that may not follow the exact mask. Decision: normalize output dimensions and perform deterministic server-side compositing with a fixed 3 px feathered alpha ramp. Masked drift scoring excludes that same 3 px band so it does not measure Clai's own seam treatment.

5. **The named FLUX successor has shipped, but it does not replace Fill's contract.** BFL now recommends FLUX.2 for generation and multi-reference editing, and provides fixed snapshot endpoints, but its documented editing input has references rather than a hard mask. The fal `fal-ai/flux-pro/v1/fill` endpoint remains live. BFL's current general endpoint list no longer advertises a direct base `flux-pro-1.0-fill` endpoint, so the implementation should use fal for Fill and not assume the direct BFL URL is supported without a live authenticated contract test.

6. **Provider endpoint and price details in the brief are stale.** fal currently documents separate Nano Banana Pro generate/edit endpoints and lists $0.15 per standard image ($0.30 at 4K), not approximately $0.13. Prices belong in metering configuration/provider responses, not constants in domain logic.

7. **SAM endpoint mismatch.** `fal-ai/sam-3/image` returns PNG mask files; `fal-ai/sam-3/image-rle` returns the RLE string/list the proposed data model expects. Recommendation: use the RLE endpoint and specify one canonical RLE dialect after a real response fixture is captured; “RLE” alone is not enough to guarantee decoder compatibility.

8. **P0 acceptance and P3 scope conflict.** P0 requires verification by drift score, while drift score is scheduled for P3. Recommendation: implement the immutable metric storage and a baseline unmasked scorer in P0 for acceptance; P3 adds warnings, richer UI, regression dashboards, rebase, and masked scoring.

9. **“Exact reruns” is too strong for mutable hosted model aliases.** A prompt, seed, params, and input snapshot reconstruct a request, but cannot guarantee identical pixels after a provider silently changes weights or preprocessing. Recommendation: store exact endpoint/model identifiers plus provider response metadata and call the feature “reconstruct run” unless a pinned provider snapshot is available.

10. **Broken chips conflict with hard node deletion and cascading edges.** The existing database deletes edges with their source node, which makes a broken chip impossible to render. Recommendation: soft-delete nodes that still have incoming connect references and preserve the edge/chip tombstone; hard-delete only nodes with no dependents.

11. **Version deletion must account for more than pinned base edges.** Historical `inputSnapshot` records also reference versions, and reproducibility requires their artifacts. Recommendation: never hard-delete a version row or artifact in v1; mark it hidden from ordinary version strips while retaining all provenance and dependency targets.

12. **The current graph has no safe automatic semantic migration.** Existing generic edges do not say base versus connect, and prompt/image/3D nodes cannot be losslessly converted into the unified node. Recommendation: preserve projects but reset the current placeholder graph rows during the architecture migration. If existing development canvases matter, approve an explicit export or migration policy instead; do not infer edge roles.

13. **The storage prerequisite is missing from the build order.** P0 cannot create durable immutable versions without owning the output artifact. Recommendation: include minimal object-storage ingestion in implementation P0 even though storage remains an orthogonal adapter.

14. **`canvasId` has no corresponding current or target aggregate.** Recommendation: use the existing project ID as `canvasId` in the API contract for now. Adding both Project and Canvas would introduce an unrequested ownership layer.

15. **Novel-viewpoint refusal is removed.** Decision: v1 has no refusal, classifier, viewpoint feature, or run-parameter flag. Viewpoint prompts flow through the ordinary edit path. Revisit only if usage data establishes a real product problem.

## Provider verification on 2026-09-03

- fal documents Nano Banana Pro generation at `fal-ai/nano-banana-pro` and editing at `fal-ai/nano-banana-pro/edit`; both accept a seed, and edit accepts a list of images: [fal Nano Banana Pro API](https://fal.ai/docs/model-api-reference/image-generation-api/nano-banana-pro).
- fal lists Nano Banana Pro at $0.15 per 1K/2K image and $0.30 at 4K: [fal Nano Banana Pro model](https://fal.ai/models/fal-ai/nano-banana-pro/edit).
- fal's live FLUX Fill schema requires exactly one image and one same-sized mask and supports a seed: [fal FLUX.1 Fill API](https://fal.ai/models/fal-ai/flux-pro/v1/fill/api).
- BFL's deprecation notice names `flux-pro-1.0`, depth, canny, and the finetuned Fill endpoint, while its current docs recommend FLUX.2 and still describe FLUX.1 Fill as targeted editing: [BFL release notes](https://docs.bfl.ai/release-notes), [BFL model overview](https://docs.bfl.ai/quick_start/introduction).
- FLUX.2 is available and supports multi-reference editing, but its documented edit contract does not expose a hard mask: [BFL FLUX.2 editing](https://docs.bfl.ai/flux_2/flux2_image_editing).
- fal exposes a dedicated SAM 3 RLE endpoint with text, point, and box prompts: [fal SAM 3 RLE API](https://fal.ai/models/fal-ai/sam-3/image-rle/api).
- OpenAI documents GPT Image 2 edits with multiple images and a mask applied to the first image, while warning that the mask is prompt guidance rather than an exact boundary: [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation).
- Meshy 7 is a valid current Image-to-3D model, but returned model URLs are downloadable provider assets and should be copied to durable storage: [Meshy Image-to-3D API](https://docs.meshy.ai/en/api/image-to-3d).

## Implementation phases

Each implementation phase remains independently shippable and should be one PR. “Audit Phase 0” in this document is distinct from product implementation P0 below.

### P0-zero — provider thesis spike

Completed before production changes. The retained report and evidence are at `.progress/p0-zero-spike/REPORT.md`.

- Produced 100 successful pairs from 20 licensed product photos across four categories and five prescribed edit classes.
- Applied the exact preservation preamble, retained input/output pairs and provider request metadata, visually reviewed every pair, and computed DINOv2 cosine similarity.
- Overall cosine was `0.9375`; the five shoe recolors averaged `0.9301` and all visibly retained the same footwear identity/configuration.
- Observed three instruction failures, operation-dependent score behavior, wrong-surface selection for inapplicable material prompts, local/background drift, and a deterministic branded-image policy rejection.
- Discarded the throwaway runner and retained the 100-pair seed corpus for drift regression work.
- Proposed before production P0: qualify the preservation list as applying to every **unmentioned** attribute, because the static preamble's “preserve lighting direction” instruction conflicts with the prescribed relight edit. This wording change is pending approval.

### Implementation P0 — thesis and durable foundation

- Add the normalized node, edge, version, metric, and run-job schema, insert-only version enforcement, role/pin constraints, and the approved legacy-graph migration policy.
- Preserve Project, React Flow pan/zoom/rendering behavior, Redis/Celery, and health checks.
- Add pure resolution, all-six-row operation routing, prompt building, seed resolution, edit-depth calculation, and request freezing.
- Add durable artifact storage ingestion.
- Add the fal Nano Banana Pro adapter with separate generate/edit endpoints and capability validation.
- Add run submit/status flow through the existing Celery worker, idempotent commit, and retry/reconciliation behavior.
- Replace the split prompt/image UI with one runnable design node containing prompt, active artifact, base thumbnail, version strip, and pre-run resolved-op chip.
- Support base edges pinned to a selected version, base replacement on a second drag, branch creation from a historical version, and immutable version append.
- Add a baseline unmasked drift metric so P0's stated acceptance can be evaluated.
- Tests: all operation rows plus invalid states, edge cardinality under concurrency, pinned versus active resolution, seed precedence, no ancestor-prompt inheritance, preservation preamble, immutable version DB trigger, job idempotency, provider contract fixtures, and the navy-shoe integration path with a fake provider.

### Implementation P1 — masking

- Add brush, lasso, and rectangle mask editing over the active/base version.
- Add SAM 3 click/text/box selection via `fal-ai/sam-3/image-rle` and canonical RLE validation.
- Add stale-mask detection as a blocking resolution error; never downgrade it to an unmasked op.
- Add RLE-to-provider-mask rendering with black-preserve/white-edit semantics and same-dimension validation.
- Add FLUX Fill for `edit_inpaint`, plus feathered outside-mask compositing and pixel-diff scoring outside the feather band.

### Implementation P2 — connect and composition

- Add at most two ordered connect edges following source active versions.
- Implement atomic chip editing with a stable edge ID behind each chip; wire and chip mutations share one server operation.
- Add broken source tombstones, run blocking, hover highlighting, and pan-to-node behavior.
- Add positional prompt construction and `[base, connect 0, connect 1]` payload order.
- Route `generate_ref` and `edit_ref_guided` to Nano Banana Pro edit.
- Add the GPT Image 2 adapter and route `edit_composite` according to approval gate 3, with capability tests proving mask and reference inputs are present.
- Auto-title on the first successful run and allow inline rename. Before that, use a visible deterministic placeholder title.

### Implementation P3 — trust and branching integrity

- Surface drift score and threshold policy; add regression fixtures and provider-change monitoring.
- Add edit-depth warning around the approved threshold and explicit rebase/collapse as a new run against the root base.
- Add branch markers and jump navigation on the linear version strip.
- Add version hiding/dependency counts while retaining provenance artifacts.
- Make fan-out from a selected version the primary branch gesture.

### Implementation P4 — derived 3D and metering

- Add a 3D view toggle on a selected version, not a node type.
- Add the Meshy adapter and persist copied mesh assets in a version-keyed derived record.
- Add provider failover policy, explicit reason reporting, and capability-aware selection.
- Add actual provider usage/cost records per run and aggregate them per node; do not rely on static price estimates.

## Existing file disposition

Files are listed once under exactly one required heading. “ADAPT” may include a rename or merge when the existing responsibility survives but the current file boundary does not.

## KEEP

- `.gitignore` — correct secret, cache, build, and progress exclusions.
- `backend/.dockerignore` — correct Python build-context exclusions.
- `backend/.python-version` — Python 3.12 remains the backend baseline.
- `backend/Dockerfile` — current uv-based runtime structure remains valid; dependency changes flow through the lockfile.
- `backend/alembic.ini` — keep the migration configuration.
- `backend/alembic/README` — keep the migration-directory documentation.
- `backend/alembic/env.py` — keep metadata-driven migrations and environment URL injection.
- `backend/alembic/script.py.mako` — keep the Alembic revision template.
- `backend/alembic/versions/31d1d8b844ba_add_graph_nodes_and_edges.py` — immutable migration history; supersede with a forward migration.
- `backend/alembic/versions/8b2b19d1243a_create_projects.py` — immutable migration history and retained Project aggregate.
- `backend/app/__init__.py` — keep the application package marker.
- `backend/app/api/__init__.py` — keep the API package marker.
- `backend/app/api/health.py` — preserve process, database, and queue dependency readiness checks.
- `backend/app/api/projects.py` — retain project list/create/read behavior; ownership is orthogonal and currently absent.
- `backend/app/core/__init__.py` — keep the core package marker.
- `backend/app/core/database.py` — keep the SQLAlchemy engine/session boundary.
- `backend/app/models/project.py` — Project remains the canvas aggregate; retain thumbnail support.
- `backend/app/schemas/__init__.py` — keep the schema package marker.
- `backend/app/schemas/project.py` — retain the existing project contracts.
- `backend/app/services/__init__.py` — keep and populate this service package.
- `backend/app/workers/__init__.py` — keep the worker package marker.
- `backend/tests/__init__.py` — keep the test package marker.
- `backend/tests/test_health.py` — retain health and Celery registration coverage.
- `backend/tests/test_projects.py` — retain project behavior coverage.
- `frontend/.dockerignore` — keep frontend build-context exclusions.
- `frontend/.gitignore` — keep Next.js-specific exclusions.
- `frontend/Dockerfile` — keep the Node 22/npm application image structure.
- `frontend/app/icon.svg` — retained brand asset.
- `frontend/app/layout.tsx` — retained root shell and metadata boundary.
- `frontend/app/page.tsx` — retained projects home composition.
- `frontend/app/projects/[id]/loading.tsx` — retained project loading state.
- `frontend/app/projects/[id]/not-found.tsx` — retained project not-found state.
- `frontend/components/graph/save-status.tsx` — retain save-state presentation.
- `frontend/components/projects/new-project-button.tsx` — retain project creation flow.
- `frontend/components/projects/project-grid.tsx` — retain project grid/empty state.
- `frontend/components/projects/project-tile.tsx` — retain project navigation and thumbnail display.
- `frontend/eslint.config.mjs` — keep strict Next.js lint configuration.
- `frontend/lib/projects.ts` — retain project client/server reads.
- `frontend/next.config.ts` — no architectural change required yet.
- `frontend/postcss.config.mjs` — retain Tailwind PostCSS wiring.
- `frontend/tsconfig.json` — strict mode is already enabled and remains required.

## ADAPT

- `.env.example` — add fal, object-storage/CDN, optional OpenAI/BFL, Meshy, webhook, and provider-selection settings without exposing secrets.
- `.progress/current.md` — replace the pre-refactor status with this audit, provider findings, baseline verification, and approval gate.
- `Makefile` — extend test commands with frontend unit tests and PostgreSQL constraint/integration tests while preserving existing workflows.
- `README.md` — document the unified node/version architecture, scoped APIs, run lifecycle, provider setup, storage prerequisite, and phase status.
- `backend/pyproject.toml` — add runtime HTTP/provider, image/RLE/hash, storage, and scoring dependencies plus any PostgreSQL integration-test tooling.
- `backend/uv.lock` — regenerate only from the approved dependency changes.
- `backend/app/core/config.py` — add typed provider, object-storage/CDN, webhook, timeout, retry, and feature-selection settings.
- `backend/app/main.py` — register scoped node/edge/run/version/mask routes and provider webhook handling.
- `backend/app/models/__init__.py` — export normalized node, edge, version, run, metric, and mesh models.
- `backend/app/models/graph.py` — replace generic node/edge records with the normalized target fields and database constraints; move version/run/derived records into focused model files if needed.
- `backend/app/schemas/graph.py` — replace open JSON node data and generic edges with strict discriminated node/edge/pin/mask/version read contracts.
- `backend/app/api/graph.py` — keep aggregate reads but replace destructive full-document writes with scoped, invariant-preserving mutations.
- `backend/app/workers/celery_app.py` — preserve Celery configuration and add task discovery/routing; generation task logic belongs in separate worker modules.
- `backend/tests/conftest.py` — retain fast pure/unit fixtures but add PostgreSQL-backed fixtures for partial indexes, triggers, locking, and JSONB behavior.
- `backend/tests/test_graph.py` — replace placeholder node-type tests with target node/edge/pin/cardinality/stale-mask/refcount/API tests.
- `docker-compose.yml` — preserve PostgreSQL, Redis, API, worker, and frontend services; add provider/storage environment wiring and a local object-store option only if approved.
- `frontend/app/globals.css` — preserve React Flow canvas styling and add design-node, version, chip, mask, drift, stale, and broken-reference states.
- `frontend/app/projects/[id]/page.tsx` — hydrate the new aggregate graph contract and keep current load/error behavior.
- `frontend/components/graph/add-node-control.tsx` — create only the unified runnable design node; remove Prompt/Image/3D type choices.
- `frontend/components/graph/graph-workspace.tsx` — preserve rendering, pan, zoom, selection, and drag behavior while moving to role/pin edges, scoped persistence, branching, resolved-op previews, and server-authoritative mutations.
- `frontend/components/graph/image-node.tsx` — merge artifact display into the unified design-node component and version strip.
- `frontend/components/graph/node-frame.tsx` — add role-specific handles, base thumbnail area, op/status indicators, and inline title while retaining the common frame.
- `frontend/components/graph/prompt-node-actions.tsx` — broaden/rename to typed design-node actions for prompt, run, active version, mask, title, and chip operations.
- `frontend/components/graph/prompt-node.tsx` — evolve/rename into the unified design node with prompt, artifact, run state, versions, and base subject.
- `frontend/lib/graph.ts` — replace generic React Flow persistence types and full PUT with strict target contracts, conversion helpers, preview logic, and scoped API clients.
- `frontend/package.json` — add unit-test scripts/dependencies and only the minimal editor/image dependencies selected during implementation.
- `frontend/package-lock.json` — regenerate from the approved package changes.

## DELETE

- `backend/alembic/versions/.gitkeep` — the migrations directory is no longer empty.
- `frontend/components/graph/model-node.tsx` — 3D as a node type directly violates the target; P4 reintroduces it as a version-scoped view toggle.

## Approval requested

Approval of this plan should explicitly confirm or revise:

- Project ID is the brief's `canvasId`.
- Version facts are immutable; metrics and meshes live in separate derived tables.
- Only base/version and connect/active role-pin pairs are valid in v1.
- `edit_composite` and its GPT Image 2 adapter are deferred to P2; FLUX Fill is reserved for single-base inpainting.
- Masked provider outputs are feather-composited before storage when exact outside-mask pixels are required, and drift scoring excludes the feather band.
- Existing placeholder graph rows may be reset while Project rows are retained.
- Minimal durable object storage and baseline drift scoring move into implementation P0 because its acceptance criteria require them.

After the P0-zero spike is reported and confirmed, begin implementation P0 only. Do not begin P1 masking until P0 is working and accepted.
