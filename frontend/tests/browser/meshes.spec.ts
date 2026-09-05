import { expect, test } from "@playwright/test";
import type { ModelViewerElement } from "@google/model-viewer";

test("3D is opt-in, defaults to grey geometry and caches only its exact image version", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:8109/reset");
  await request.post("http://127.0.0.1:8109/many-versions");
  let submissions = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/mesh"))
      submissions++;
  });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.getByRole("button", { name: "3D form", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: /Standard textures/ }),
  ).not.toBeChecked();
  await expect(
    page.getByText("The rear and hidden sides are inferred", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Generate 3D · $0.20" }).click();
  await expect
    .poll(() =>
      page
        .locator("model-viewer")
        .evaluate((element) => (element as ModelViewerElement).loaded),
    )
    .toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.locator("model-viewer")).toHaveCount(0);
  await source.getByRole("button", { name: "3D form", exact: true }).click();
  await expect(
    page.getByText("Cached for this exact image version.", { exact: false }),
  ).toBeVisible();
  expect(submissions).toBe(1);
  await page.keyboard.press("Escape");
  await source
    .getByRole("button", { name: "Select version 14", exact: true })
    .click();
  await expect(
    source.getByRole("button", { name: "2D image" }),
  ).toHaveAttribute("aria-pressed", "true");
  await source.getByRole("button", { name: "3D form", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Generate 3D · $0.20" }),
  ).toBeVisible();
  expect(submissions).toBe(1);
});
