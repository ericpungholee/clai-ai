import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:8109/reset");
});

test("rectangle, brush, lasso, undo, empty selection and version binding", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await page.getByRole("button", { name: "Select an area to edit" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Save mask", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Select an area first");
  const canvas = dialog.locator("canvas");
  const box = (await canvas.boundingBox())!;
  for (const tool of ["rectangle", "brush", "lasso"]) {
    await dialog.getByRole("button", { name: tool, exact: true }).click();
    await page.mouse.move(box.x + 150, box.y + 110);
    await page.mouse.down();
    await page.mouse.move(box.x + 270, box.y + 110, { steps: 5 });
    await page.mouse.move(box.x + 270, box.y + 170, { steps: 5 });
    await page.mouse.move(box.x + 150, box.y + 170, { steps: 5 });
    await page.mouse.up();
    if (tool !== "lasso")
      await dialog.getByRole("button", { name: "Undo", exact: true }).click();
  }
  await dialog.getByLabel("Area to select").fill("nothing");
  await dialog.getByRole("button", { name: "Select ·" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Nothing matched");
  await dialog.getByRole("button", { name: "Save mask", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  const graph = await (
    await request.get(
      "http://127.0.0.1:8109/api/projects/fixture-project/graph",
    )
  ).json();
  expect(graph.nodes[1].mask).toMatchObject({
    subject_version_id: "subject",
    width: 480,
    height: 360,
  });
  expect(graph.nodes[1].mask.rle).not.toBe("");
  await request.post("http://127.0.0.1:8109/stale");
  await page.reload();
  await expect(
    page.locator('[data-id="target"]').getByRole("alert"),
  ).toContainText("different subject version");
  await expect(
    page
      .locator('[data-id="target"]')
      .getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
});
