# Canvas cleanup review

The same two-node fixture has one pinned subject and one reference from the source to the edit node. Both nodes have one version. Captures use a 1440 × 1000 viewport and fixed canvas transforms, so the card and wire differences can be compared at exactly 100% and 40% scale. The grayscale captures apply a grayscale filter to the canvas.

| Scale | Before | After |
| --- | --- | --- |
| 100% | [Color](before-100.png) | [Color](after-100.png) |
| 40% | [Color](before-40.png) | [Color](after-40.png) |
| 100%, grayscale | [Grayscale](before-100-grayscale.png) | [Grayscale](after-100-grayscale.png) |
| 40%, grayscale | [Grayscale](before-40-grayscale.png) | [Grayscale](after-40-grayscale.png) |

The subject and reference now occupy separate tracks at 35% and 70% of each card, with filled versus hollow endpoints, solid versus dashed strokes, different arrowheads, and matching prompt numbers. Origin reference numbering starts at 1 because that is the existing compiled prompt order; connecting a subject moves references to 2 and 3.

The single-version strip is hidden. Hide and branch navigation remain in the header menu for that case; a hidden version remains accessible through the retained-count control. Restoring the only version also selects it when no image is active. Before the first edit run, the pinned subject supplies the preview and mask toolbar. Image-viewer changes are limited to adding the comparison selector.

Node deletion removes the card immediately, waits behind any current save, and uses the existing endpoint. Retained subjects appear as ghost chips; deleted references appear as red broken wire stubs. Subject disconnection uses the existing mask and subject endpoints in sequence, clearing the mask first. No new API shape, persistence timer, restore route, or canvas undo stack is introduced.

To regenerate the after captures:

```sh
cd frontend
npx playwright test tests/browser/ui-screenshots.spec.ts
```
