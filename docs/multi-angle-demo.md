# Multi-angle demo pipeline

The primary image appears as soon as its ordinary provider call completes. That
transaction also creates three queued angle records. The Celery worker then
dispatches independent right, back, and left image-edit tasks, all using the
primary image as their only image input and carrying the frozen design prompt.
Each task ingests one separate artifact into the existing storage system.
Auxiliary tasks create no graph nodes. The user-facing run stays in progress until
all three tasks finish; it then reports complete, or failed if an angle failed.

The expanded image viewer shows a four-slot gallery, readiness counts, and failed
or unavailable angles. Selecting a thumbnail changes the inspected/downloaded
image. The existing graph poll refreshes open viewers by version ID. The canvas
continues showing the primary image. Iteration and branching follow the existing
new-draft/new-version flow and produce their own angle records.

## Schema

- `Version.artifact_url` remains the canonical primary/front image.
- `VersionImageView` / `version_image_views` uses `(version_id, angle)` as its
  primary key, with angle restricted to `right`, `back`, or `left`. It retains
  artifact storage metadata, the primary reference URL, provider request details,
  status, errors, and timestamps from the earlier rear-view implementation.
- Version responses expose `views: { front, right?, back?, left? }`, where each
  entry contains `image_url` and `status`. Only completed artifacts expose URLs.
- `VersionMesh.source_image_urls` freezes the ordered four inputs when an attempt
  is queued. The mesh API refuses incomplete angle sets.
- Migration `d2b9a71f403e` follows the existing `c8e4f1a09b3d` migration, renames
  and expands the rear table, retains saved rear artifacts as `back`, and converts
  frozen primary/rear mesh inputs to the JSON list. No historical backfill is run.

The migration was applied to the local demo database and the idle worker restarted
during implementation. For other running installations, use `make migrate` and
`docker compose restart worker` after updating the code.

## Provider requests

Auxiliary edits use `fal-ai/nano-banana-pro/edit` with the primary artifact uploaded
as the only `image_urls` entry, `num_images: 1`, and `limit_generations: true`.
Prompts request right/left 60-degree three-quarter and back 180-degree camera
moves, matching identity, proportions, materials, colors, graphics, and scale, a
centered single object and simple background, with no duplicates, collages, or
contact sheets. They include the original design specification, bind graphics to
their original surfaces, and forbid invented materials or construction layers.
The [documented edit input schema](https://fal.ai/models/fal-ai/nano-banana-pro/edit/api)
has no explicit camera-angle control, so this implementation uses distinct prompts.

With exactly four complete images, `fal-ai/trellis-2/multi` receives:

```json
{
  "resolution": 1536,
  "texture_size": 4096,
  "ss_sampling_steps": 12,
  "shape_slat_sampling_steps": 12,
  "tex_slat_sampling_steps": 12,
  "image_urls": [
    "<uploaded front image>",
    "<uploaded right image>",
    "<uploaded back image>",
    "<uploaded left image>"
  ]
}
```

The worker logs the exact model ID, preset, multi-image flag, image count, all
uploaded input URLs, resolution, texture size, and each sampling-step value before
each input upload and before the model request. Before submission, a multi-view
job rejects the wrong endpoint, a missing or duplicated view, and any singular
`image_url`. A four-view job must send exactly four distinct `image_urls`.

Missing or failed angles block 3D generation. Each artifact is read and uploaded
separately. The [TRELLIS-2 multi-image OpenAPI schema](https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/trellis-2/multi)
requires `image_urls` on `/fal-ai/trellis-2/multi` and describes conditioning averaged
across views, with no required camera ordering. The root `/fal-ai/trellis-2` route
requires `image_url` and cannot enable multi-image input by adding `image_urls`.
The demo `high_quality` preset uses the five numeric settings above; other options
retain provider defaults. Only historical versions with no angle records retain
the existing Tripo request with `image_url`. TRELLIS-2's `model_glb` result uses
the existing GLB validation and storage.
A new attempt upgrades a completed multi-view cache when its model or preset
settings are outdated. Identical attempts and jobs already in progress stay idempotent.
The provider result is saved before GLB validation and artifact storage. If those
steps fail, Retry reuses that completed result instead of submitting another paid
fal generation. Queue result polling runs once per second rather than using the
SDK's high-frequency default.

## Files changed for the four-view extension

| Area | Files |
| --- | --- |
| Version schema and persistence | `backend/app/models/{graph,__init__}.py`, `backend/app/schemas/graph.py`, `backend/app/services/graph_service.py`, `backend/app/api/graph.py`, new migration `backend/alembic/versions/d2b9a71f403e_version_image_views.py` |
| Generation and dispatch | `backend/app/services/run_execution.py`, `backend/app/services/image_view_jobs.py` (generalized from `rear_image_jobs.py`), `backend/app/workers/celery_app.py`, `backend/app/providers/nano_banana.py`, `backend/app/services/prompt_builder.py` |
| 3D inputs and upgrades | `backend/app/api/meshes.py`, `backend/app/providers/mesh.py`, `backend/app/services/mesh_jobs.py` |
| UI and contracts | `frontend/lib/{graph,meshes}.ts`, `frontend/components/graph/{graph-workspace,image-viewer,mesh-viewer}.tsx` |
| Verification | `backend/tests/test_image_views.py` (expanded from rear-image tests), `test_meshes.py`, `test_provider_storage.py`, `test_run_core.py`, `test_postgres_invariants.py`, `frontend/tests/fake-api.ts`, new `frontend/tests/browser/image-views.spec.ts` |
| Documentation | `README.md`, `architecture.md`, this document |

Existing unrelated workspace modifications were retained. The prior rear-view
migration and TRELLIS adapter were already present as uncommitted work.

## Verification and limits

- Backend tests exercise primary availability while user-facing completion waits,
  all four
  files attached to one version, independent branch/iteration sets, exactly ordered
  separate TRELLIS inputs, rejection of partial sets, legacy single-image fallback,
  frozen inputs, cache upgrades, and duplicate delivery without duplicate calls.
- PostgreSQL tests cover migrations/invariants, including preservation of existing
  rear images and frozen mesh inputs, using the dedicated `postgres-test` service.
- Playwright covers the live-updating gallery with pending/failed/complete angles,
  switching legacy active versions, no additional canvas nodes, inspecting each
  angle, mesh upgrade availability, normal generation/iteration and mesh polling.
- Backend Ruff checks, frontend ESLint/TypeScript, and frontend unit checks are run.

The initial live request failed with HTTP 422 because the application sent the
four-view payload to the single-image root route. The route is now corrected to
`fal-ai/trellis-2/multi`, verified against fal's public OpenAPI metadata. Regression
tests cover this routing error, dropped/duplicated inputs, singular fallback, and
upgrades from cached older models or lower-quality presets. No schema migration
is needed for this routing fix. The corrected live request completed from four
separate inputs and returned a 17.9 MB textured GLB. TRELLIS-2 references embedded
WebP textures through `EXT_texture_webp`; the validator now recognizes that standard
extension and ingested the existing result without another paid generation. The
exact request and result are recorded in `docs/trellis-request-verification.json`.

Each generation adds three image-edit calls. Image models can invent hidden
geometry or graphics; prompts cannot guarantee exact identity. The primary is
treated as front without forcing the user's usual generation viewpoint. Old
versions show their saved views only. Caught failures remain visible and do not
block the primary or other angles. Worker termination can leave an angle pending;
this demo scope does not add a recovery scheduler or automatic angle retries.
The backend development server reloads source changes automatically, while the
Celery worker must be restarted after worker/provider/storage code changes.

The live example was a symmetric skateboard deck. It verifies transport, routing,
ingestion, and UI availability, but does not prove that multi-image reconstruction
is visually better than the prior single-image result. A fair visual comparison
still needs the same asymmetric design generated once with each input mode.
