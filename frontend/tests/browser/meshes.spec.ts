import { expect, test } from "@playwright/test";
import type { ModelViewerElement } from "@google/model-viewer";

test("3D uses image textures by default and caches only its exact image version", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:8109/reset");
  await request.post("http://127.0.0.1:8109/many-versions");
  let submissions = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/mesh")) {
      expect(request.postDataJSON().texture).toBe("standard");
      expect(request.url()).toContain("/versions/version-15/mesh");
      submissions++;
    }
  });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(
    page.getByText("Colors and print included.", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Hidden sides are inferred and may vary.", { exact: false }),
  ).toBeVisible();
  expect(submissions).toBe(0);
  await page.getByRole("button", { name: "Generate 3D" }).click();
  await expect
    .poll(() =>
      page
        .locator("model-viewer")
        .evaluate((element) => (element as ModelViewerElement).loaded),
    )
    .toBe(true);
  expect(
    await page
      .locator("model-viewer")
      .evaluate((element) =>
        Boolean(
          (element as ModelViewerElement).model?.materials[0]
            .pbrMetallicRoughness.baseColorTexture?.texture,
        ),
      ),
  ).toBe(true);
  await expect(
    page.getByRole("img", { name: "Original 2D image used for this 3D view" }),
  ).toHaveAttribute("src", "http://127.0.0.1:8109/artifacts/subject.svg");
  await page.keyboard.press("Escape");
  await expect(page.locator("model-viewer")).toHaveCount(0);
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "3D view", exact: true }),
  ).toBeVisible();
  expect(submissions).toBe(1);
  await page.keyboard.press("Escape");
  await source
    .getByRole("button", { name: "Select image 14", exact: true })
    .click();
  await expect(source.getByRole("group", { name: "Image view" })).toHaveCount(
    0,
  );
  await expect(
    source.getByRole("button", { name: "Inspect result" }).getByRole("img"),
  ).toHaveAttribute("src", "http://127.0.0.1:8109/artifacts/subject.svg");
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.getByRole("button", { name: "Generate 3D" })).toBeVisible();
  expect(submissions).toBe(1);
});

test("a cached grey model can be regenerated with image colors and print", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:8109/reset");
  await request.post(
    "http://127.0.0.1:8109/api/projects/fixture-project/versions/subject/mesh",
    { data: { attempt_id: "old-grey-attempt", texture: "no" } },
  );
  let submissions = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/mesh")) {
      expect(request.postDataJSON().texture).toBe("standard");
      expect(request.postDataJSON().attempt_id).not.toBe("old-grey-attempt");
      submissions++;
    }
  });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  const upgrade = page.getByRole("button", {
    name: "Generate with colors & print",
  });
  await expect(upgrade).toBeVisible();
  expect(submissions).toBe(0);
  await upgrade.click();
  await expect(upgrade).toHaveCount(0);
  await expect
    .poll(() =>
      page
        .locator("model-viewer")
        .evaluate((element) =>
          Boolean(
            (element as ModelViewerElement).model?.materials[0]
              .pbrMetallicRoughness.baseColorTexture?.texture,
          ),
        ),
    )
    .toBe(true);
  await page.keyboard.press("Escape");
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "3D view" }),
  ).toBeVisible();
  await expect(upgrade).toHaveCount(0);
  expect(submissions).toBe(1);
});
