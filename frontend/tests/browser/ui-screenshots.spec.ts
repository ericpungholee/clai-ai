import { expect, test } from "@playwright/test";

test("two wire roles at 100% and 40% in color and grayscale", async ({
  page,
  request,
}) => {
  const api = "http://127.0.0.1:8109";
  await request.post(`${api}/reset`);
  await request.put(`${api}/api/projects/fixture-project/nodes/target/prompt`, {
    data: {
      expected_revision: 0,
      document: [
        { type: "connect", edge_id: "reference", source_node_id: "source" },
        { type: "text", text: ". Keep the same shade proportions." },
      ],
    },
  });
  await request.post(`${api}/api/projects/fixture-project/nodes/target/runs`, {
    data: { idempotency_key: "screenshot" },
  });
  await request.post(`${api}/finish-run`);
  await page.goto("/projects/fixture-project");
  await expect(page.locator(".react-flow__edge")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Inspect result" }),
  ).toHaveCount(2);
  await page
    .locator('.react-flow__node[data-id="target"] img')
    .first()
    .evaluate((img: HTMLImageElement) => img.decode());
  await page.mouse.move(1400, 50);
  // Fixed presentation transforms make before/after captures directly comparable.
  // Interactive zoom and hit targets are covered separately by the canvas suite.
  for (const zoom of [1, 0.4]) {
    for (const grayscale of [false, true]) {
      await page.locator(".react-flow__viewport").evaluate(
        (element, { zoom, grayscale }) => {
          (element as HTMLElement).style.transform =
            `translate(350px, 100px) scale(${zoom})`;
          (element as HTMLElement).style.filter = grayscale
            ? "grayscale(1)"
            : "none";
        },
        { zoom, grayscale },
      );
      await page.screenshot({
        path: `../docs/ui-cleanup/${process.env.CLAI_SCREENSHOT_PHASE ?? "after"}-${zoom * 100}${grayscale ? "-grayscale" : ""}.png`,
      });
    }
  }
});
