import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8109";
test.beforeEach(async ({ request }) => {
  await request.post(`${api}/reset`);
});
test.afterEach(async ({ request }) => {
  await request.post(`${api}/reset`);
});

test("primary stays visible while angle gallery updates and handles a failed view", async ({ page, request }) => {
  await request.post(`${api}/image-views`, { data: { state: "pending" } });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.getByRole("button", { name: "Inspect result" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("img", { name: "Desk lamp — Front view" })).toBeVisible();
  await expect(dialog.getByText("Angles for 3D · 1/4 ready")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Show Right view" })).toBeDisabled();
  await request.post(`${api}/image-views`, { data: { state: "partial" } });
  await expect(dialog.getByText("Angles for 3D · 3/4 ready")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Show Back view" })).toBeDisabled();
  await expect(dialog.getByText("Unavailable")).toBeVisible();
  await dialog.getByRole("button", { name: "Show Right view" }).click();
  await expect(dialog.getByRole("img", { name: "Desk lamp — Right view" })).toHaveAttribute("src", /angle=right/);
  await request.post(`${api}/image-views`, { data: { state: "complete" } });
  await expect(dialog.getByText("Angles for 3D · 4/4 ready")).toBeVisible();
  await dialog.getByRole("button", { name: "Show Back view" }).click();
  await expect(dialog.getByRole("img", { name: "Desk lamp — Back view" })).toHaveAttribute("src", /angle=back/);
  await page.keyboard.press("Escape");
  await expect(source.locator('.image-preview img').first()).toHaveAttribute("src", `${api}/artifacts/subject.svg`);
  await expect(page.locator(".react-flow__node")).toHaveCount(2);
});

test("switching saved versions loads that version's angle set", async ({ page, request }) => {
  await request.post(`${api}/many-versions`);
  await request.post(`${api}/image-views`, { data: { version_id: "subject", state: "complete" } });
  await request.post(`${api}/image-views`, { data: { version_id: "version-15", state: "complete" } });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  for (const [number, id] of [[15, "version-15"], [1, "subject"], [15, "version-15"]] as const) {
    await source.getByRole("button", { name: `Select image ${number}`, exact: true }).click();
    await source.getByRole("button", { name: "Inspect result" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button", { name: "Show Left view" }).click();
    await expect(dialog.getByRole("img", { name: "Desk lamp — Left view" })).toHaveAttribute("src", `${api}/artifacts/subject.svg?angle=left&version=${id}`);
    await page.keyboard.press("Escape");
  }
});

test("3D generation stays disabled until every angle is ready", async ({ page, request }) => {
  await request.post(`${api}/image-views`, { data: { state: "pending" } });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  const waiting = page.getByRole("button", { name: "Waiting for image angles" });
  await expect(waiting).toBeDisabled();
  await expect(
    page.getByText("3D generation starts after all image angles finish."),
  ).toBeVisible();

  await request.post(`${api}/image-views`, { data: { state: "complete" } });
  await expect(page.getByRole("button", { name: "Generate 3D" })).toBeEnabled();
});

test("a single-view mesh can be upgraded when the angles finish", async ({ page, request }) => {
  let inputCount = 1;
  let submissions = 0;
  await page.route(`${api}/api/projects/fixture-project/versions/subject/mesh`, (route) => {
    if (route.request().method() === "POST") {
      submissions += 1;
      inputCount = 4;
    }
    return route.fulfill({ json: {
      version_id: "subject", attempt_id: `attempt-${inputCount}`, texture: "standard",
      status: "complete", artifact_url: `${api}/artifacts/mesh.glb`, preview_url: null,
      elapsed_seconds: 1, error: null, input_image_count: inputCount,
    } });
  });
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.locator(".image-preview").hover();
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await request.post(`${api}/image-views`, { data: { state: "complete" } });
  await page.getByRole("button", { name: "Regenerate with 4 views" }).click();
  await expect(page.getByRole("button", { name: "Regenerate with 4 views" })).toHaveCount(0);
  expect(submissions).toBe(1);
});
