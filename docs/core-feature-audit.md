# Core feature audit — 2026-09-13

> Historical configuration. Current image/mesh behavior is documented in [the image-to-3D flow](image-to-3d-preview.md).

Audited image generation/editing, references and frozen inputs, masks/SAM, image history and branching, mesh submission/cache/ingestion, logo overlays, artifact storage, graph persistence/polling, and worker configuration. This audit builds on the uncommitted provider, multiview and logo work already present in the workspace.

## Findings and fixes

| Severity | Finding | Change |
| --- | --- | --- |
| High | Every image required four paid image requests across three dependent stages, at Sunburst/max and 2048². Two saved successful runs averaged **331.21 seconds**. | New drafts use Flare/high at 1024² and one image request. Fine detail and four-view generation remain explicit UI options. Existing explicit sizes remain intact. |
| High | Invented back/side images were fed into TRELLIS as though they were observations. Averaging inconsistent evidence can reinforce category-associated components. | Default reconstruction uploads only the immutable source image. Synthetic and legacy extra views never enter that payload. The inspected UofT deck source has no wheels or trucks. The live TRELLIS test still invented mounting pieces, so Hunyuan 3D v3.1 Rapid is now the default after passing this example's component check. |
| High | TRELLIS always requested maximum geometry/texture resolutions and 550K target vertices. | Defaults are 1024 geometry, 2048 texture and 100K vertices, keeping 12-step sampling. This reduces requested work and browser geometry; wall-clock improvement needs measurement. |
| High | A corrupt frozen run failed before failure recording and could remain queued. | Decode after a durable claim, inside the failure handler. Invalid snapshots fail without a provider call. |
| Medium | A successful first side submission could lose its ID if the second submission failed. | Record each view job immediately before submitting the next. There remains an unavoidable submission/DB-write crash window without provider idempotency. |
| Medium | Concurrent graph/mesh polling could overlap and discard late responses; repeated graph polls could indefinitely outdate each other. | Schedule the next poll after the preceding request finishes. Stop scheduling on unmount/terminal mesh states. |
| Medium | Graph reads, mesh status reads and collapse preview unnecessarily acquired project write locks. | Read paths no longer lock projects; graph mutations retain serialization. |
| Medium | A cached bad mesh had no ordinary replacement action. | Add **Regenerate 3D**. Repeated identical attempts and active-job requests reuse the same job; a deliberate completed-cache replacement gets a new attempt. |
| Medium | Historical front-only images were blocked from 3D by four-view requirements. | Reconstruct from their saved source, without modifying immutable history. |
| Medium | An optional preview failure discarded an already validated GLB. | Log preview failure and retain the successful mesh. Reject invalid GLB JSON chunk lengths. |
| Medium | Reference uploads were sequential. | Upload concurrently with bounded workers and preserve input order in the submitted URL list. |
| Low | Long tasks could reserve queued work ahead of other workers and retain redundant Celery results. | Prefetch one task per worker process; ignore Celery results because PostgreSQL owns job state. |
| Low | SAM ignored configured fal timeouts. | Use the same configured transport/queue limits. |
| Low | Routing still emitted an unsupported masked-plus-reference operation. | Reject the combination at routing; retain historical `edit_composite` vocabulary for stored versions. |
| Low | Architecture docs still described removed measurements and mandatory maximum-quality multiview generation. | Remove stale measurement diagram entry and document the actual settings and input policy. |

The old Nano Banana and FLUX Fill adapters were already deleted in the incoming workspace. Their removal is retained; current imports/tests do not depend on them. Historical migrations and operation names are retained because installed databases and immutable versions depend on them. The large canvas coordinator is active code, not safe dead-code deletion.

## Models and what we feed them

| Use | Selection | Rationale and actual input |
| --- | --- | --- |
| Interactive images | GPT Image 2.5 **Flare**, high | Current generation/edit model recommended by fal for most applications. Receives the compiled user instruction, explicit image dimensions, one PNG output, and ordered subject/reference images when editing. |
| Fine image detail | GPT Image 2.5 **Sunburst**, max | Explicit opt-in for precision work. Same contract; higher latency is intentional. |
| Masked edits | Selected GPT Image variant | Subject converted to PNG, matching alpha mask with transparent editable pixels. Deterministic compositing preserves original pixels outside the selection. |
| 3D default | **Hunyuan 3D v3.1 Rapid**, source-only | Original image, textures enabled, additional PBR maps disabled. Its live deck output had no added hardware. OBJ/material/texture outputs are converted locally to a self-contained GLB. |
| Faster 3D alternative | **TRELLIS.2**, source-only | Supported numeric settings and original image only. Faster in the live test, but invented underside hardware; select explicitly when that tradeoff is acceptable. |
| Region selection | **SAM 3**, image-RLE | Source bytes, text/points and bounded mask count; existing RLE orientation tests pass. |

fal's [GPT Image 2.5 comparison](https://fal.ai/gpt-image-2.5) describes Flare as the interactive default and Sunburst as the slower precision variant. Its advertised 50% latency reduction compares Flare with GPT Image 2, **not** this application's former four-request Sunburst pipeline. [Flare's edit schema](https://fal.ai/models/openai/gpt-image-2.5/flare/edit/api) supports the reference/mask contract and quality settings. Neither variant exposes an image seed through this API; recorded seeds are history metadata, not reproducibility guarantees.

[FLUX.2 Klein 9B](https://fal.ai/models/fal-ai/flux-2/klein/9b/edit/api) is an alternative for fast four-step edits. It was not substituted into masked/precision editing without fidelity evidence. [Hunyuan 3D v3.1](https://fal.ai/hunyuan-3d) offers Rapid for a single image and Pro for named multi-angle inputs. These are credible 3D alternatives; being newer or labeled Pro does not establish better fidelity or lower latency on this particular deck. After the approved live comparison, Hunyuan 3D v3.1 Rapid becomes the default: it preserved the deck-only geometry better. TRELLIS.2 remains selectable, not an automatic fallback. Model choice is frozen into the mesh row before enqueueing.

The [TRELLIS.2 API](https://fal.ai/models/fal-ai/trellis-2/api) explicitly describes resolution/texture/vertex-count tradeoffs. Higher resolution and guidance are not a semantic constraint against additional parts. The app's 100K-vertex choice favors a useful product preview while retaining more detail than fal's suggested 20K–50K web/mobile range.

There is no defensible universal “best model” claim from endpoint documentation alone. The selected defaults target this application's interactive speed and preservation requirements. Model-specific prompts and schema checks are verified; the two-model deck comparison supports the selected default for this case, but does not rank every fal model across product categories.

## Regression coverage

Validation: **135 backend tests**, **8 PostgreSQL tests**, **4 frontend unit tests**, and **45 browser scenarios** pass (the original 44-scenario suite plus new controls coverage and targeted reruns after mesh changes). Ruff, formatting, ESLint, TypeScript and the production frontend build pass. The idle local Celery worker was reloaded to activate the final code/dependencies. Existing canvas images and caches were not rewritten.

Backend tests cover default and precision payloads, frozen model choices, legacy snapshot compatibility, mask pixels/alpha, reference order, source-only reconstruction even when a generated four-view set exists, immediate view ID recording, corrupt jobs, cache regeneration/idempotency, GLB/preview failures, artifact boundaries and existing core flows. PostgreSQL tests exercise migrations, immutable versions and concurrency invariants. Browser tests cover project CRUD, reference editing, masks, branching, draft conflicts, image/mesh exports, multiview inspection, polling and generation settings.

## Remaining limits

- Learned 3D priors can still hallucinate unseen geometry. Source-only conditioning cannot recover a physically exact back from a front photograph. Inspect the exported GLB from all sides before claiming a component-count guarantee.
- Four-view generation is an explicit slower visualization feature. Its outputs remain generated hypotheses; the current UI has no way to certify them as real observations. A verified-manifest branch exists for trusted externally supplied data, but generators never mark their outputs verified.
- Optional four-view runs still wait for all requested images and fail atomically if one fails. A failed run can leave stored orphan artifacts. No retention/garbage-collection service was introduced.
- No durable transactional outbox or automatic provider-resume workflow exists. A crash between enqueue/submission and recording can require inspection. Automatic resubmission could cause duplicate charges, so it remains disabled. A local queue timeout does not cancel remote inference.
- Image provider elapsed time measures the front request; total elapsed includes optional views and ingestion. Mesh metadata now separates preparation and provider time. There is no historical mesh timing baseline in the inspected local database.
- Logo overlays preserve source pixels in the viewer but are **not baked into downloaded GLBs**. Existing controls and honest export labeling are retained.
- Full-graph polling still loads retained history; large projects may need incremental synchronization. Network calls have server-side timeouts, but browser requests do not yet have a common explicit timeout policy.
- Existing mesh attempts share one mutable cache row; regeneration replaces cache metadata, not image history. Stored older artifact files remain.
- The project remains a local, single-user application without authentication, rate limits or billing controls; that is outside this audit's requested feature fixes.

## Live validation

Two paid tests were explicitly approved: one Flare/high image request using the existing deck instruction and one TRELLIS.2 reconstruction using the original UofT deck image. The image completed in **21.66 seconds**; TRELLIS reconstruction and ingestion completed in **48.31 seconds** and produced a 4,474,284-byte GLB. The exported geometry has one mesh and 96,225 triangles. These are individual observations, not a statistical benchmark. The former 331.21-second image average includes four generated views and larger output, so the difference is not a model-only comparison.

The Flare image is a bare deck. The TRELLIS GLB **failed visual acceptance**: front/back/oblique renders without decals reveal invented underside mounting pieces and distorted artwork. Source-only conditioning did not eliminate the model's priors. The additionally approved Hunyuan 3D v3.1 Rapid comparison produced a deck with **no trucks, wheels or mounting pieces** in front/back/oblique inspection. fal reported **89.594 seconds of inference**; local download/conversion added a few seconds. Its converted output has one mesh and 50,000 triangles. The front logo is materially closer to the source, but the unobserved backside repeats/invents graphics. This is improved component fidelity for this example, not a universal accuracy guarantee.

Hunyuan returned OBJ plus MTL/PNG despite the `model_glb` field name. The new converter uses trimesh with an in-memory resolver limited to declared allowlisted downloads, embeds texture assets into GLB, and sets the diffuse material to nonmetallic. Omitting that last factor causes the glTF metallic default to darken an otherwise valid diffuse texture. The conversion submits no new inference. Hunyuan reference dimensions/size are validated before upload.

Outputs and request IDs are saved separately from the canvas in ignored local `.data/audit/generation-check.json`; GLB screenshots are `.data/audit/deck-views.png` and `.data/audit/hunyuan-deck-views.png`. No automatic retries are used.
