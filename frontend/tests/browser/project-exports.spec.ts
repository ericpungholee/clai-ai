import { expect, test } from "@playwright/test";

const api = "http://127.0.0.1:8109";
test.beforeEach(async ({ request }) => { await request.post(`${api}/reset`); });

test("projects can be renamed, cancelled, and deleted", async ({ page }) => {
  await page.goto("/");
  const tile = page.locator(".project-tile");
  await tile.getByRole("button", { name: /^Options for/ }).click();
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await tile.getByRole("textbox", { name: "Project name" }).fill("New lamp");
  await tile.getByRole("button", { name: "Save", exact: true }).click();
  await expect(tile.getByRole("heading", { name: "New lamp", exact: true })).toBeVisible();
  await page.reload();
  await expect(tile.getByRole("heading", { name: "New lamp", exact: true })).toBeVisible();
  await tile.getByRole("button", { name: /^Options for/ }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(tile).toHaveCount(1);
  await tile.getByRole("button", { name: /^Options for/ }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await page.getByRole("button", { name: "Delete project", exact: true }).click();
  await expect(page.getByText("No projects yet", { exact: true })).toBeVisible();
});

test("canvas exports the original image and the saved GLB", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  const imageDownload = page.waitForEvent("download");
  await source.getByRole("button", { name: "Export image", exact: true }).click();
  expect((await imageDownload).suggestedFilename()).toMatch(/\.svg$/);
  await source.getByRole("button", { name: "3D", exact: true }).click();
  await expect(page.getByRole("button", { name: "Export mesh only · GLB" })).toHaveCount(0);
  await page.getByRole("button", { name: "Generate 3D" }).click();
  const exportModel = page.getByRole("button", { name: "Export mesh only · GLB" });
  await expect(exportModel).toBeVisible();
  const meshDownload = page.waitForEvent("download");
  await exportModel.click();
  expect((await meshDownload).suggestedFilename()).toMatch(/\.glb$/);
});

test("failed image exports show an error and can be retried", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  await page.route("**/artifacts/subject.svg", route => route.fulfill({ status: 500 }));
  const source = page.locator('.react-flow__node[data-id="source"]');
  await source.getByRole("button", { name: "Export image", exact: true }).click();
  await expect(source.getByRole("alert")).toContainText("Could not download");
  await page.unroute("**/artifacts/subject.svg");
  const download = page.waitForEvent("download");
  await source.getByRole("button", { name: "Export image", exact: true }).click();
  await download;
  await expect(source.getByRole("alert")).toHaveCount(0);
});

test("canvas project title autosaves on blur and reloads", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  const rename = page.getByRole("button", { name: /^Rename project:/ });
  await rename.click();
  await page.getByRole("textbox", { name: "Project name", exact: true }).fill("Cancelled title");
  await page.keyboard.press("Escape");
  await expect(rename).not.toContainText("Cancelled title");
  await rename.click();
  const nameField = page.getByRole("textbox", { name: "Project name", exact: true });
  await nameField.fill("Sky lamp");
  await expect(page.getByRole("button", { name: "Save project name" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Cancel rename" })).toHaveCount(0);
  await nameField.blur();
  await expect(rename).toHaveText("Sky lamp");
  await page.reload();
  await expect(rename).toHaveText("Sky lamp");
  await page.getByRole("link", { name: "← Projects" }).click();
  await expect(page.locator(".project-tile").getByRole("heading", { name: "Sky lamp" })).toBeVisible();
});
