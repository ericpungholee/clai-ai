# Historical canvas captures

These before/after screenshots document an earlier UI review. Their controls and appearance are historical, not the current specification. See [architecture.md](../../architecture.md) for the current implementation and [lifecycle notes](../node-lifecycle/README.md) for image retention/migration behavior.

| Scale | Original | Before this revision | After |
| --- | --- | --- | --- |
| 100% | [Color](before-100.png) | [Color](before-revision-100.png) | [Color](after-100.png) |
| 40% | [Color](before-40.png) | [Color](before-revision-40.png) | [Color](after-40.png) |
| 100%, grayscale | [Grayscale](before-100-grayscale.png) | [Grayscale](before-revision-100-grayscale.png) | [Grayscale](after-100-grayscale.png) |
| 40%, grayscale | [Grayscale](before-40-grayscale.png) | [Grayscale](before-revision-40-grayscale.png) | [Grayscale](after-40-grayscale.png) |

The screenshot test now writes fresh captures to ignored Playwright output directories, leaving this historical evidence unchanged:

```sh
cd frontend
npx playwright test tests/browser/ui-screenshots.spec.ts
```
