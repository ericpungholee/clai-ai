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
      expect(request.postDataJSON().model).toBe("trellis");
      expect(request.url()).toContain("/versions/version-15/mesh");
      submissions++;
    }
  });

  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  expect(submissions).toBe(0);
  for (const title of ["Hero / front", "Front-right 45°", "Rear-right 135°", "Rear-left 225°", "Front-left 315°"]) {
    await expect(page.getByRole("img", { name: title, exact: true })).toBeVisible();
  }
  await page.getByRole("button", { name: "Generate 3D" }).click();
  await waitForViewer(page);
  expect(submissions).toBe(1);
  await expect(page.getByRole("img", { name: "Isolated logo crop" })).toHaveCount(0);
  await expect(
    page.getByRole("img", { name: "Original 2D image used for this 3D view" }),
  ).toBeVisible();

  await page.keyboard.press("Escape");
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await waitForViewer(page);
  expect(submissions).toBe(1);

  const regenerate = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/mesh"));
  await page.getByRole("button", { name: "Regenerate 3D", exact: true }).click();
  expect((await regenerate).postDataJSON().regenerate).toBe(true);
  await waitForViewer(page);
  expect(submissions).toBe(2);

  await page.keyboard.press("Escape");
  await source
    .getByRole("button", { name: "Select image 14", exact: true })
    .click();
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.getByRole("button", { name: "Generate 3D" })).toBeVisible();
  expect(submissions).toBe(2);
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

test("original logo pixels render automatically, survive reload, and remain removable", async ({ page, request }, testInfo) => {
  await request.post("http://127.0.0.1:8109/reset");
  await request.post("http://127.0.0.1:8109/logo-fixture");
  const meshUrl = "http://127.0.0.1:8109/api/projects/fixture-project/versions/subject/mesh";
  let saves = 0;
  let selections = 0;
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().endsWith("/mesh/logo")) saves++;
    if (request.url().endsWith("/selection")) selections++;
  });
  async function open() {
    const source = page.locator('.react-flow__node[data-id="source"]');
    await source.locator(".image-preview").hover();
    await source.getByRole("button", { name: "3D", exact: true }).click();
  }
  async function savedDecal() {
    return (await (await request.get(meshUrl)).json()).logo_preservation.decal;
  }
  async function originalInkPixels(screenshot: Buffer) {
    return page.evaluate(async (png) => {
      const image = await createImageBitmap(await (await fetch(png)).blob());
      const canvas = document.createElement("canvas");
      canvas.width = image.width;
      canvas.height = image.height;
      const context = canvas.getContext("2d")!;
      context.drawImage(image, 0, 0);
      const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
      let count = 0;
      // The crest ink is #f5f2df; the unrelated base texture has different colors.
      for (let i = 0; i < data.length; i += 4)
        if (Math.abs(data[i] - 245) < 4 && Math.abs(data[i + 1] - 242) < 4 && Math.abs(data[i + 2] - 223) < 4) count++;
      return count;
    }, `data:image/png;base64,${screenshot.toString("base64")}`);
  }
  await page.goto("/projects/fixture-project");
  await open();
  await page.getByRole("button", { name: "Generate 3D" }).click();
  await waitForViewer(page);
  await expect(page.getByRole("button", { name: "Move logo", exact: true })).toBeVisible();
  await expect.poll(async () => (await savedDecal())?.placement).toBeTruthy();
  expect(selections).toBe(0);
  const stored = await savedDecal();
  expect(stored.source.url).toContain("logo-bear.png");
  expect(stored.crop.dataUrl).toContain("logo-crop.png");
  const canvas = page.getByRole("img", { name: "Interactive 3D mesh" });
  await expect.poll(async () => originalInkPixels(await canvas.screenshot())).toBeGreaterThan(25);
  await testInfo.attach("preserved-logo", {
    body: await canvas.screenshot({ path: testInfo.outputPath("preserved-logo.png") }),
    contentType: "image/png",
  });

  // A full reload discards the workspace's in-memory decal map.
  const beforeReload = saves;
  await page.reload();
  await open();
  await waitForViewer(page);
  await expect(page.getByRole("button", { name: "Move logo", exact: true })).toBeVisible();
  await expect.poll(async () => originalInkPixels(await canvas.screenshot())).toBeGreaterThan(25);
  expect(saves).toBe(beforeReload);
  expect(await savedDecal()).toEqual(stored);
  await page.getByRole("slider", { name: "Logo rotation" }).fill("17");
  await expect.poll(async () => (await savedDecal()).rotation).toBe(17);
  await page.getByRole("button", { name: "Remove logo" }).click();
  await expect.poll(savedDecal).toBeNull();
  await expect.poll(async () => originalInkPixels(await canvas.screenshot())).toBe(0);
  await testInfo.attach("raw-base-texture", {
    body: await canvas.screenshot({ path: testInfo.outputPath("raw-base-texture.png") }),
    contentType: "image/png",
  });
  await page.reload();
  await open();
  await waitForViewer(page);
  await expect(page.getByRole("img", { name: "Isolated logo crop" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export mesh only · GLB" })).toBeVisible();
});
