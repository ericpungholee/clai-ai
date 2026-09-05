# Clai architecture

The consolidated implementation brief defines the current scope. The implementation is reviewed in one branch against `main`; the earlier phase workflow is retired.

## Boundaries

- A project owns a canvas of drafts and frozen image results. New nodes produce at most one image; failed runs leave their drafts editable.
- Input edges pin an image; reference edges resolve a source image when a run is submitted. One input and at most two references are permitted. Reference chips and wires save atomically.
- The canvas is the history. Ordinary runs never inherit ancestor prompts. Input resolution, operation routing, and prompt construction are pure; submission freezes their result under a project mutation lock before enqueue.
- Workers dispatch frozen requests and ingest provider artifacts before committing the node's image. API guards and worker commit checks prevent a second image. Paid submissions are never automatically retried.
- PostgreSQL rejects image UPDATE and DELETE. Metrics and mesh caches live separately. Node deletion retains historical artifacts used downstream.
- Continue editing creates a draft to the right from the result. Try another copies its original input and draft below with a stored fresh seed and submits. Revise prompt copies below without submitting.
- Explicit chain collapse creates a visible editable draft against the root; it adds no hidden context to ordinary runs.

## Providers

- Generate and unmasked edits use fal Nano Banana Pro's separate generation and editing endpoints.
- Partial area selections use fal FLUX Fill. SAM 3 image-rle supplies click/text selection; brush, lasso, and rectangle work locally. Selections bind to input images, and stale selections block runs.
- Selected edits are composited over the original with a 3px outer feather band. Results display outside-band pixel change. Unmasked drift remains internal regression telemetry.
- Tripo 3D uses standard image color/print textures with PBR and texture alignment. Each image owns its cached first-party GLB and preview. Older grey models can be regenerated with textures; hidden surfaces remain inferred.

## Compatibility and delivery

Area selections and references exclude each other in both the UI and API. Collapse supports plain instruction-edit chains. Existing multi-image nodes retain a read-only image strip and cannot run; draft references resolve their selected image at submission, while completed runs keep their recorded inputs.

Apply the Alembic migrations before serving the new build. The final migration restores an image on legacy nodes whose presentation was cleared and removes obsolete visibility preferences, without splitting nodes or deleting image artifacts.

[README](README.md) covers setup. [Lifecycle notes](docs/node-lifecycle/README.md) contain the migration details, validation results, and workflow capture. Tests use provider doubles and do not make paid calls.
