# Phase A preamble check

2026-09-04. Exactly eight Nano Banana Pro edit submissions completed: four existing fixtures, old and candidate preambles, the same input, instruction, seed and settings in each pair. No paid retries or additional tuning calls.

The local image report is `.progress/p0-5-preamble-ab/report.html`. It presents the original, old output and candidate output at matching display sizes with links to the full files. Raw requests, request IDs, responses and downloaded outputs are retained alongside `manifest.json` in that directory. The image corpus remains local, as with P0.

| Instruction | Old | Candidate | Preservation observation |
| --- | --- | --- | --- |
| Make the base of the water bottle square | No clear footprint change | No clear footprint change | Both redraw table texture; input already has a rectangular body, making this fixture less decisive |
| Make the toe box square | Visible squared toe | Similar squared toe | Pair arrangement and background remain recognizable |
| Make each chair back a single flat wooden panel | Both panels changed | Both panels changed | Woven seats retained; candidate uses stronger panel grain |
| Make the mouse body a rectangular slab with square corners | Slab-like silhouette | Slab-like silhouette, slightly rounder corners | Both extend the body beyond the right frame edge |

These are visual observations, not quality scores. This small paired check does not establish superiority of the candidate. The background/framing findings were reported before adoption; the production preamble is unchanged pending direction. No historical prompts were rewritten.

The exact tested candidate remains in `backend/scripts/live_preamble_ab.py`. The runner refuses to reuse an existing output directory, preventing accidental paid reruns.

Other Phase A corrections were mostly already on main: subject vocabulary and migration, generate-only white-background prompt construction, no resolved-operation chip, and subject-aware placeholders. This phase hides the ineffective white-background control on edits, gives new nodes a concrete example instruction, exercises all four edit routes for absence of a white-background clause, and proves both UPDATE and DELETE are still blocked after the rename migration.
