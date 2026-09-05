# Clai architecture

The completion brief and its Tripo amendment are the current scope. Auth, deployment, billing, collaboration, mesh edges and extra providers are excluded.

## Boundaries

- A project owns a canvas of image nodes. Each node has a mutable draft and a linear list of immutable versions.
- Subject edges pin a version; connect edges follow active. One subject and at most two connects. Connect chips and wires are saved in one transaction.
- The graph is the memory. Ordinary runs never inherit ancestor prompts or read provenance. Resolution, classification and prompt construction are pure; submission freezes their result under a project mutation lock before enqueue.
- Workers dispatch the frozen request only. Provider inputs are uploaded from first-party bytes, and outputs are ingested before a version is committed. Paid submissions are never automatically retried.
- PostgreSQL rejects version UPDATE and DELETE. Metrics, mesh caches and visibility live in separate version-keyed tables. Deletion retains historical artifacts and broken references.
- Explicit chain collapse creates a visible editable draft against the root; it does not add hidden context to ordinary runs.

## Providers

- Generate and unmasked edits: fal Nano Banana Pro, separate generate/edit endpoints.
- Partial masks: fal FLUX Fill. SAM 3 image-rle supplies click/text selection; brush, lasso and rectangle work locally. Masks bind to subject versions; stale masks block. Full masks normalize to unmasked edits after validation.
- Masked output is composited over the original with a 3px outer feather band. Only outside-band pixel drift appears in the UI. Unmasked drift is internal, operation-specific regression telemetry.
- 3D: `tripo3d/tripo/v2.5/image-to-3d`, untextured by default ($0.20), standard textures opt-in ($0.30). The exact version owns its cached first-party GLB and preview. Hidden surfaces are inferred, not designed.

## Deliberate limits

FLUX Fill accepts no connect images. Mask + connect combinations are blocked before enqueue; neither input is silently discarded and no extra provider is introduced. Collapse supports plain instruction-edit chains; masked/reference chains cannot safely replay their regions and image ordinals against a different root.

The reported eight-call preamble A/B was followed by user authorization to finish. Future edits use the tested narrower wording; historical prompts are unchanged. The A/B did not establish superiority or guarantee background/framing preservation. Only composited masked edits offer an exact outside-band pixel guarantee.

## Delivery

Six stacked phase PRs cover A corrections, B masking, C chips, D branching/trust, E 3D and F canvas completion. The final cleanup belongs to F. See `.progress/current.md` for verification and measured provider latency; README contains local setup. Database migrations and focused invariant tests are retained. One-off paid runners and proof galleries are removed.
