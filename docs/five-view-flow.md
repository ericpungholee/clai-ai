# Five-view image-to-3D flow

Implemented and exercised against fal on 2026-09-13. This supersedes the image/mesh policies in the earlier audit documents. It adapts the existing Clai Version, RunJob and VersionMesh flow; no Vril backend, new state system, migration or interpretation layer was added.

## Behavior and model selection

The inspected workspace generated a front, then a back, then left/right orthographic views referencing the front/back pair. Extra views were optional. The mesh worker excluded generated views unless explicitly marked verified, so even generated sets normally reconstructed from only the front. Hunyuan was the default and automatic logo extraction ran after reconstruction.

New image runs now freeze Sunburst/max and five views, including when the draft still contains earlier speed settings. Already frozen jobs retain their recorded settings. The UI displays the current policy and no longer offers cheaper image or alternative reconstruction choices. Provider failures surface without model fallback or automatic paid retries.

| Stage | Exact fal endpoint | Settings |
| --- | --- | --- |
| Canonical hero generation | `openai/gpt-image-2.5/sunburst/text-to-image` | GPT Image 2.5 Sunburst, `quality=max`, one PNG, default 1024×1024 |
| Hero edits / four supporting views | `openai/gpt-image-2.5/sunburst/edit` | Same model and quality; each supporting request has exactly one reference: the stored hero |
| Reconstruction | `fal-ai/trellis-2/multi` | Five raw images; resolution 1536, texture size 4096, decimation target 500,000; 12 steps per stage; structure/shape guidance 8, texture guidance 1; remesh enabled with full projection |

Selection is supported by [OpenAI's image generation guide](https://developers.openai.com/api/docs/guides/image-generation), which identifies Sunburst for editing precision. The [fal Sunburst generation schema](https://fal.ai/models/openai/gpt-image-2.5/sunburst/text-to-image/api) and [edit schema](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api) confirm the exact endpoints, reference input, PNG output and maximum quality. The [live TRELLIS.2 multi-image OpenAPI schema](https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai%2Ftrellis-2%2Fmulti), retrieved directly during this task, confirms the `/multi` path, image list without a four-image cap, 1536/4096 settings, and parameter bounds. These sources establish availability and intended use, not a comparative visual benchmark proving universal superiority.

The supporting order is `front_right` (45°), `rear_right` (135°), `rear_left` (225°), `front_left` (315°). All four requests are submitted before waiting, and all use the exact same uploaded hero. None references another supporting image or includes the original category prompt. Prompts preserve physical shape, proportions, thickness, material, component count, graphics and spelling; unobserved surfaces use simple continuations. Missing components are intentional. There are no skateboard-specific branches or prompt rules.

After live testing exposed a rear-right image that still depicted the front, rear prompts were strengthened to require back/side surfaces, put the hero-facing front out of sight, and hide graphics confined to that front. This final prompt revision has **not** completed a live retest: fal rejected the retest before any supporting job was accepted because the account had exhausted its credits.

## Storage, reconstruction inputs and inspection

- The hero remains `Version.artifact_url` with its existing storage key and SHA-256.
- `Version.provider_response_metadata.views` holds all five immutable URLs: `front`, `front_right`, `rear_right`, `rear_left`, `front_left`.
- `view_jobs` records each supporting model, endpoint, request ID, payload, canonical reference URL, output storage key and SHA-256. Each accepted submission is recorded before the next submission is attempted.
- A failed supporting view or byte-identical duplicate prevents publication of a partial image version. Hash checks do not detect semantically wrong cameras or near-duplicate images.
- The mesh API validates completeness, rejects missing/legacy four-view sets with a regenerate-image message, and stores `VersionMesh.provider_response_metadata.source_views` before enqueue. Cached old GLBs remain viewable.
- The worker validates the Version's complete set, records it before upload, uploads every original file without changing its bytes, and submits all five uploaded URLs in the defined order as `request_payload.image_urls`. It sends no prompt, category, negative prompt, camera reasoning, segmentation, crop, collage or inferred geometry to TRELLIS.
- **Inspect result** switches among the five originals with zoom and original-file download. **3D → Images used for 3D** shows all five before generation and links to the full files. Mesh GET/POST responses expose `source_views` while queued, running, failed and complete. The persisted provider payload identifies the corresponding fal upload URLs.

Standard images are stored byte-for-byte. An existing masked edit still performs Clai's deterministic mask compositing to create its canonical hero; every supporting image references that final saved hero. No reconstruction preprocessing is added.

Automatic logo extraction is removed from this reconstruction path. Existing saved decals and manual source-pixel selection remain available. They are viewer overlays and are not baked into the downloaded GLB. The live evaluations below use the provider GLB without decals. Because input-camera consistency is not yet fully resolved, no new logo post-process was added.

## Live verification

Three real runs exercised the application API, frozen image run execution, artifact ingestion, Version commit, mesh API, TRELLIS worker and GLB ingestion in isolated test databases. No production project records were modified. The model selection and payloads match the table above. Local originals, per-request provenance, mesh requests, GLBs, review pages and screenshots are under `.data/multiview-verification/`. The report files contain exact prompts and artifact mappings.

| Case | Five input images | Raw GLB result |
| --- | --- | --- |
| Bare skateboard deck | No trucks, wheels, bearings or protruding hardware visible. Natural wood and deck shape remain recognizable. Similar plain front/back surfaces make the intended rear camera coverage difficult to establish. | Deck geometry has no visible wheels, trucks or protruding hardware across eight inspection directions. TRELLIS nevertheless invented a dark, mottled reverse-face texture. This passes the tested component check, not full material fidelity. |
| Blue box with star crest and `CLAI` | Crest and readable text remain recognizable where shown, but rear-right incorrectly repeats a branded front view while rear-left is plain. This fails camera consistency before reconstruction. | Box-like geometry is reconstructed, but the crest/text are lost and large faces have strongly corrupted multicolor textures. Branding acceptance fails. Cannot attribute all degradation to TRELLIS independently of the inconsistent input cameras. |
| Solid terracotta rounded block with central groove | Rounded form, color and groove remain consistent. Rotations are modest and not calibrated camera observations. | One rounded volume with the central groove is retained, with no visible separate components. Some shading/texture banding remains; exact CAD dimensions and hidden-surface accuracy are not established. |

Raw TRELLIS provider waits, excluding upload/ingestion: deck ~219 seconds, logo ~170 seconds, volume ~134 seconds. Stored GLBs are approximately 18–20 MB. These are single samples, not latency or quality benchmarks.

Artifacts for inspection:

- [Deck comparison](../.data/multiview-verification/deck/review.png), [deck provenance](../.data/multiview-verification/deck/report.json).
- [Logo comparison](../.data/multiview-verification/logo/review.png), [logo provenance](../.data/multiview-verification/logo/report.json).
- [Volume comparison](../.data/multiview-verification/volume/review.png), [volume provenance](../.data/multiview-verification/volume/report.json).
- [Blocked revised-prompt retest](../.data/multiview-verification/logo-v2/report.json).

The review pages render each raw GLB from eight directions with no decals. Their camera labels refer to renderer axes, not a claimed calibration to the generated hero. The artifacts are local and gitignored; the implementation and regression tests are in the repository.

## Automated verification and remaining limits

Validation completed: 138 backend tests passed, 8 PostgreSQL-only tests skipped; 7 targeted browser tests and 4 frontend unit tests passed. Backend lint, frontend lint/typecheck and diff whitespace checks passed.

Tests cover hero-only reference enforcement, five-view atomicity, duplicate content, malformed manifests, current model policy for old drafts, submission provenance, no fallback, unchanged stored/uploaded bytes and ordering, concurrent uploads, missing historical sets, version-specific mesh caching, manual decal persistence, mask behavior, and queue failure handling. Browser tests cover five-view switching, pre-generation inspection, mesh caching, polling and legacy decals. These contract tests do not assert visual fidelity from fake images.

The clean pipeline is implemented, but full visual acceptance remains incomplete. Sunburst may ignore the requested camera, change hidden geometry or alter prints. TRELLIS averages conditioning rather than using calibrated camera constraints; it can still introduce category priors or invent textures. Increasing texture resolution did not preserve the logo in the tested inconsistent set. There is no supported category-exclusion or exact-logo guarantee in this endpoint. Keep inspecting originals before reconstruction. The next concrete verification is to replenish the configured fal account, rerun the corrected rear prompts from the same logo hero, inspect the resulting set, and reconstruct it before evaluating any post-process.

Existing worker recovery limits remain: no outbox or provider-resume workflow, a crash window between paid submission and recording its ID, and orphan artifacts after failed image runs. This change does not add a new workflow engine to address them.
