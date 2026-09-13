import { expect, test } from "@playwright/test";

test("project SSR hydrates without cursor-tool attributes or mismatches", async ({ page, request }) => {
  await request.post("http://127.0.0.1:8109/reset");
  const hydrationErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /hydrat|server rendered|server-rendered/i.test(message.text())) {
      hydrationErrors.push(message.text());
    }
  });
  const response = await page.goto("/projects/fixture-project");
  expect(await response!.text()).not.toContain("data-cursor-ref");
  await page.getByRole("button", { name: /Rename project:/ }).click();
  await expect(page.getByRole("textbox", { name: "Project name", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("main", { name: "Project graph workspace" })).toBeVisible();
  expect(hydrationErrors).toEqual([]);
});
