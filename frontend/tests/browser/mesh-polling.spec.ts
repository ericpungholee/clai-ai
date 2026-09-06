import { expect, test, type Page } from "@playwright/test";

const api = "http://127.0.0.1:8109";
const meshPath = `${api}/api/projects/fixture-project/versions/subject/mesh`;
const source = (page: Page) =>
  page.locator('.react-flow__node[data-id="source"]');

async function openMesh(page: Page) {
  await source(page).locator(".image-preview").hover();
  await source(page).getByRole("button", { name: "3D", exact: true }).click();
}
async function ready(page: Page) {
  await expect(page.getByRole("button", { name: "Reset view" })).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Select logo in source image" }),
  ).toBeEnabled();
}
test("mesh polling runs every two seconds, stops on close, and reopens the same worker job", async ({
  page,
}) => {
  const polls: number[] = [];
  let complete = false;
  const submissions: string[] = [];
  await page.route(meshPath, (route) => {
    if (route.request().method() !== "GET")
      submissions.push(route.request().method());
    polls.push(Date.now());
    return route.fulfill({
      json: {
        version_id: "subject",
        attempt_id: "worker-job",
        texture: "no",
        elapsed_seconds: null,
        error: null,
        status: complete ? "complete" : "provider_pending",
        artifact_url: complete ? `${api}/artifacts/grey-mesh.glb` : null,
        preview_url: complete ? `${api}/artifacts/subject.svg` : null,
      },
    });
  });
  await page.goto("/projects/fixture-project");
  await openMesh(page);
  await expect(
    page.getByText("Safe to close — this keeps running."),
  ).toBeVisible();
  await expect
    .poll(() => polls.length, { timeout: 7000 })
    .toBeGreaterThanOrEqual(3);
  expect(polls[2] - polls[1]).toBeGreaterThan(1700);
  expect(polls[2] - polls[1]).toBeLessThan(2600);
  await page.keyboard.press("Escape");
  const count = polls.length;
  await page.waitForTimeout(2300);
  expect(polls.length).toBe(count);
  complete = true;
  await openMesh(page);
  await ready(page);
  expect(submissions).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(
    source(page).getByRole("group", { name: "Image view" }),
  ).toBeVisible();
});
