import { expect, test } from "@playwright/test";

test("fifteen numbered versions stay navigable, inspectable, comparable and retained", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:8109/reset");
  await request.post("http://127.0.0.1:8109/many-versions");
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await expect(
    source.getByRole("button", { name: "Select version 15", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await source.getByRole("button", { name: "Inspect active image" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("img")).toHaveCSS(
    "transform",
    /1.25/,
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await source.getByRole("button", { name: "Inspect active image" }).click();
  await page.getByLabel("Compare active version to").selectOption("subject");
  await expect(page.getByRole("dialog").getByRole("img")).toHaveCount(2);
  await page.keyboard.press("Escape");
  await source.getByRole("button", { name: "Version 15 actions" }).focus();
  await source
    .getByRole("button", { name: "Version 15 actions" })
    .press("Enter");
  await page
    .getByRole("button", { name: "Hide version 15", exact: true })
    .click();
  await expect(
    source.getByRole("button", { name: "Select version 15", exact: true }),
  ).toHaveCount(0);
  await source.getByRole("button", { name: "Show retained" }).click();
  await source.getByRole("button", { name: "Version 15 actions" }).focus();
  await source
    .getByRole("button", { name: "Version 15 actions" })
    .press("Enter");
  await page
    .getByRole("button", { name: "Restore version 15", exact: true })
    .click();
  await expect(
    source.getByRole("button", { name: "Select version 15", exact: true }),
  ).toBeVisible();
});
