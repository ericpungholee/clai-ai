import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:8109/reset");
});

test("typing a chip creates a wire and backspace removes the atomic chip with its wire", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  const editor = page
    .locator('[data-id="target"]')
    .getByRole("textbox", { name: "Design prompt" });
  await editor.click();
  await editor.press("End");
  await editor.press("@");
  await page.getByRole("button", { name: "Desk lamp", exact: true }).click();
  await expect(editor.locator('[contenteditable="false"]')).toHaveText(
    "2@Desk lamp",
  );
  await expect(page.locator(".react-flow__edge")).toHaveCount(2);
  await editor.press("End");
  await editor.press("Backspace");
  await editor.press("Backspace");
  await expect(editor.locator('[contenteditable="false"]')).toHaveCount(0);
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await expect(
    page.getByRole("status", { name: "Saved", exact: true }).first(),
  ).toBeVisible();
  const graph = await (
    await request.get(
      "http://127.0.0.1:8109/api/projects/fixture-project/graph",
    )
  ).json();
  expect(
    graph.nodes[1].document.every(
      (part: { type: string }) => part.type === "text",
    ),
  ).toBe(true);
});
