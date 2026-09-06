import { expect, test, type Page } from "@playwright/test";

async function waitForViewer(page: Page) {
  await expect(
    page.getByRole("img", { name: "Interactive 3D mesh" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset view" })).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Select logo in source image" }),
  ).toBeEnabled();
}

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
  expect(submissions).toBe(0);
  await page.getByRole("button", { name: "Generate 3D" }).click();
  await waitForViewer(page);
  expect(submissions).toBe(1);
  await expect(
    page.getByRole("img", { name: "Original 2D image used for this 3D view" }),
  ).toBeVisible();

  await page.keyboard.press("Escape");
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await waitForViewer(page);
  expect(submissions).toBe(1);

  await page.keyboard.press("Escape");
  await source
    .getByRole("button", { name: "Select image 14", exact: true })
    .click();
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
  await waitForViewer(page);
  const upgrade = page.getByRole("button", {
    name: "Generate with colors & print",
  });
  await expect(upgrade).toBeVisible();
  expect(submissions).toBe(0);

  await upgrade.click();
  await expect(upgrade).toHaveCount(0);
  await waitForViewer(page);
  expect(submissions).toBe(1);

  await page.keyboard.press("Escape");
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await waitForViewer(page);
  await expect(upgrade).toHaveCount(0);
  expect(submissions).toBe(1);
});
