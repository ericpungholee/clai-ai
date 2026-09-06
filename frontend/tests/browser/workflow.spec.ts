import { expect, test } from "@playwright/test";

test("generate, continue editing, select an area, and run the edit", async ({
  page,
  request,
}) => {
  const api = "http://127.0.0.1:8109";
  await request.post(`${api}/reset`);
  await request.post(`${api}/empty-projects`);
  await page.goto("/");
  await page
    .getByRole("button", { name: "New Project", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Add node", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Design prompt" })
    .fill("A simple desk lamp");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Queued/)).toBeVisible();
  await request.post(`${api}/finish-run`);
  const results = page.locator('.design-card[data-state="result"]');
  await expect(results).toHaveCount(1);
  await results.getByRole("button", { name: "New node", exact: true }).click();
  const draft = page.locator('.design-card[data-state="draft"]');
  await draft.getByRole("button", { name: "Select area", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "rectangle", exact: true }).click();
  const box = (await dialog.locator("canvas").boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.27, box.y + box.height * 0.25);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.73, box.y + box.height * 0.55);
  await page.mouse.up();
  await dialog
    .getByRole("button", { name: "Save area selection", exact: true })
    .click();
  await expect(
    draft.getByText("Area saved. Describe the change, then Run."),
  ).toBeVisible();
  await draft
    .getByRole("textbox", { name: "Design prompt" })
    .fill("Make the shade orange");
  await draft.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Queued/)).toBeVisible();
  await request.post(`${api}/finish-run`);

  await expect(results).toHaveCount(2);
  await expect(
    results.last().getByRole("button", { name: "New node", exact: true }),
  ).toBeVisible();
});
