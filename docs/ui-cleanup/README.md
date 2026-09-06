> Historical implementation notes. The current lifecycle is documented in [One node, one image](../node-lifecycle/README.md).

# Canvas cleanup review

The same two-node fixture has one pinned subject and one reference from the source to the edit node. Both nodes have one version. Captures use a 1440 × 1000 viewport and fixed canvas transforms, so the card and wire differences can be compared at exactly 100% and 40% scale. The grayscale captures apply a grayscale filter to the canvas.

| Scale | Original | Before this revision | After |
| --- | --- | --- | --- |
| 100% | [Color](before-100.png) | [Color](before-revision-100.png) | [Color](after-100.png) |
| 40% | [Color](before-40.png) | [Color](before-revision-40.png) | [Color](after-40.png) |
| 100%, grayscale | [Grayscale](before-100-grayscale.png) | [Grayscale](before-revision-100-grayscale.png) | [Grayscale](after-100-grayscale.png) |
| 40%, grayscale | [Grayscale](before-40-grayscale.png) | [Grayscale](before-revision-40-grayscale.png) | [Grayscale](after-40-grayscale.png) |

Subject and reference wires exit at 35% and 70% of the source card. On the target, the subject lands inside its chip row and the reference lands at the prompt's vertical center. Filled versus hollow endpoints, solid versus dashed strokes, different arrowheads, and matching prompt numbers distinguish their roles. Origin reference numbering starts at 1 because that is the existing compiled prompt order; connecting a subject moves references to 2 and 3.

Cards have neutral borders; selection uses near-black ink and shadow. Only blocked cards have a colored border, in red. The subject chip animates in and out over 150 ms, with its handle following the row; an origin's available subject target sits at 30% of card height.

Run is disabled when the backend preview signature matches the active version. Local input edits invalidate the comparison immediately; previews refresh after saves, completed runs, and reference changes. A run waits for any pending upstream active-image selection. The header's Run again action submits a fresh random seed without changing the draft seed and confirms when live reference dependents will follow the result. Pinned subject dependents do not follow a new image and are excluded from that confirmation.

The single-version strip is hidden. Hide and branch navigation remain in the header menu for that case; a hidden version remains accessible through the retained-count control. Restoring the only version also selects it when no image is active. Before the first edit run, the draft has no result preview; its pinned subject remains a thumbnail with Inspect and area-selection controls. Image-viewer changes are limited to adding the comparison selector.

Node deletion removes the card immediately, waits behind any current save, and uses the existing endpoint. Retained subjects appear as ghost chips; deleted references appear as red broken wire stubs. Subject disconnection uses the existing mask and subject endpoints in sequence, clearing the mask first. Autosave remains at 500 ms, graph refresh at 3 s, and run polling at 750 ms, with serialized node saves.

The backend stores SHA-256 run signatures in the version's existing immutable input snapshot and exposes them as a version field and in run-preview. Submissions accept an optional reroll flag; ordinary request bodies are unchanged. Older versions and queued jobs without signatures remain readable and runnable. Auto-titles use the structured prompt's source titles, with five-word and 60-character limits.

To regenerate the after captures:

```sh
cd frontend
npx playwright test tests/browser/ui-screenshots.spec.ts
```
