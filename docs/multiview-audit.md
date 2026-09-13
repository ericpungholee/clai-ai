# Four-view generation and 3D audit

> Historical configuration. Current image/mesh behavior is documented in [the five-view flow](five-view-flow.md).

> Historical audit of the earlier fidelity-first configuration. The defaults and reconstruction policy below are superseded by [the core feature audit](core-feature-audit.md). Retained to explain the existing changes and their tradeoffs.

Verified 2026-09-13 against the existing fal provider stack.

## Findings and changes

- The previous worker already produced four stored images before publishing a version. The three extra edits independently inferred hidden surfaces from the front, and their provider jobs were not retained in version metadata. The new pipeline establishes the back first, then conditions both sides on the same front/back pair, with a preservation prompt that explicitly forbids assembling missing parts or inventing surface branding.
- Removed the Nano Banana Pro adapter, FLUX Fill adapter, duplicate image-payload builders and routing, and unused grayscale-mask encoder. All image operations now use one Sunburst adapter, including masked edits with the required alpha-mask semantics. Historical migration files and operation vocabulary remain because installed databases and immutable history still depend on them.
- Four immutable URLs are validated centrally. No partial version is published; byte-identical outputs are rejected. Invalid historical sets fail before mesh enqueueing. Each completed version exposes its set in the inspector. Hash checks detect exact duplicate files, not semantic inconsistency or near-duplicate viewpoints.
- TRELLIS previously used 1024 geometry and 2048 textures. It now uses the highest supported geometry and texture resolutions, 1536 and 4096, while retaining practical 12-step defaults and 550,000 target vertices. Maximum guidance and maximum sampling steps are not assumed to mean best fidelity: they can increase noise, saturation, and latency. Full remesh projection preserves more surface detail.
- Removed serial TRELLIS input-upload latency with four concurrent uploads. Both side edits are submitted before waiting and ingested concurrently. Shared front/back uploads occur once per side batch. The 3D click performs no image generation and submits one reconstruction; repeated clicks reuse its version cache.
- The SDK's unbounded queue wait could leave jobs running indefinitely despite a network timeout. Queue waits now have a configurable 900-second deadline, retain request IDs, and fail explicitly without automatic resubmission or model fallback.
- Existing source-pixel logo cropping and viewer decal controls were preserved. They are a manual/heuristic aid, not a replacement for accurate mesh textures. The downloaded GLB and preview still come from TRELLIS; viewer decals are not baked into them.

## Model and endpoint verification

- [OpenAI image-generation documentation](https://developers.openai.com/api/docs/guides/image-generation) recommends `gpt-image-2.5-sunburst` for editing precision.
- [fal Sunburst edit API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api) verifies `openai/gpt-image-2.5/sunburst/edit`, reference images, optional `mask_url`, explicit `image_size`, PNG output and `quality=max`. [fal's model comparison](https://fal.ai/gpt-image-2.5) distinguishes Sunburst's precision role from Flare's speed role and lists the text endpoint `openai/gpt-image-2.5/sunburst/text-to-image`.
- [fal's live TRELLIS.2 multi-image OpenAPI schema](https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai%2Ftrellis-2%2Fmulti) verifies the exact `/multi` endpoint, `image_urls`, averaged conditioning, 1536 geometry, 4096 textures and remesh projection. The [general TRELLIS.2 reference](https://fal.ai/docs/model-api-reference/3d-api/trellis-2) explains parameter tradeoffs. The implementation does not substitute the single-image endpoint.

No runtime fallback exists. Provider/model/endpoint and actual payloads are recorded. Sunburst's fal schema has no seed parameter: stored image seeds remain history metadata and are not sent as invented API options.

## Latency and reliability limits

Image preparation takes approximately front generation + back generation + the slower of the two side generations, plus storage and uploads. The extra dependency trades image-generation time for consistency. Sunburst at maximum quality and high-resolution TRELLIS prioritize this demo's fidelity requirements; no measured inference speedup is claimed. 3D latency is concurrent input uploads + one TRELLIS inference + ingestion and the optional local logo pass.

The pipeline enforces input provenance and completeness, not a mathematical guarantee of identical designs. Sunburst can still alter details, and TRELLIS uses learned priors despite receiving no category prompt. Its averaged conditioning is not a calibrated four-camera reconstruction constraint. No supported parameter guarantees exact printed text or forbids all extra geometry. A model result must be visually evaluated before claiming those properties.

Existing worker crash/enqueue recovery limitations remain: there is no durable outbox or provider resume UI, and a process can die between a paid submission and recording its ID. A timed-out remote generation may continue. Automatic retry is deliberately absent. Artifacts created by failed image runs are not currently garbage-collected.

## Verification and demo acceptance

Automated tests cover current endpoint/payload contracts, mask alpha direction, no fallback after provider errors, four-view atomicity, failed views, duplicate bytes, invalid historical manifests, image bytes and ordering into TRELLIS, parallel uploads, queue deadlines, version caching and inspection controls. Provider tests use deterministic doubles; they do not establish visual model quality.

Before presenting a quality claim, run a live deck-only design with asymmetric artwork and readable text. Inspect all four stored images for the same shape, materials, component count and correctly located graphics; check that the deck has no wheels or hardware in any view. Reconstruct and inspect the exported GLB from all sides, including the underside, with viewer decals disabled. Repeat with a product that has different front and back graphics and with a masked edit. Record actual provider timings and failures. Do not count the viewer-only logo overlay as export fidelity or silently regenerate an inconsistent set.
