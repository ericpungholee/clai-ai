# Single-image 3D preview

Each node creates one main image through the existing image provider. The image worker ingests it into artifact storage, commits the immutable Version, and completes the RunJob. There are no camera edit jobs or background image jobs.

Clicking Generate 3D queues a VersionMesh attempt using that Version's artifact URL. The mesh worker uploads the original bytes once and submits the current `fal-ai/trellis-2` endpoint with a singular `image_url`. This contract was verified against [fal's live single-image OpenAPI schema](https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai%2Ftrellis-2) on September 13, 2026.

Preview parameters:

- Seed: 1337
- Geometry resolution: 1024
- Texture size: 2048
- Decimation target: 50,000
- Sampling steps: 12 for each of structure, shape and texture
- Structure/shape guidance: 8; texture guidance: 1
- Remesh: false; remesh projection: 0

TRELLIS receives only the saved image, with no category prompt or extra images. The returned GLB and optional preview are validated and stored. The viewer uses provider geometry and textures directly; Export GLB downloads the stored GLB. Regeneration and color upgrades use the same main image and retain existing attempt idempotency and version-specific caching.

Legacy angle settings and metadata are ignored. Existing images and completed mesh caches remain usable. Historical database migrations are retained; no new schema migration is required.

Tests verify one image submission per run, unchanged source bytes, exactly one reconstruction upload, the endpoint and preview settings, cache isolation, retry/idempotency behavior, and the absence of angle controls in the viewer.
