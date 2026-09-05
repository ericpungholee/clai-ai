import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:8109/reset");
});

test("a fifty-node canvas supports fit, new-node and duplicate shortcuts", async ({
  page,
  request,
}) => {
  await request.post("http://127.0.0.1:8109/large-canvas");
  await page.goto("/projects/fixture-project");
  await expect(page.locator(".react-flow__node")).toHaveCount(50);
  await page
    .locator(".react-flow__pane")
    .click({ position: { x: 10, y: 400 } });
  await page.keyboard.press("f");
  await page.keyboard.press("n");
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(
              "http://127.0.0.1:8109/api/projects/fixture-project/graph",
            )
          ).json()
        ).nodes.length,
    )
    .toBe(51);
  await expect(
    page
      .getByRole("textbox", { name: "Node title" })
      .filter({ visible: true })
      .last(),
  ).toHaveValue("Untitled concept");
  await page.keyboard.press("Control+d");
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(
              "http://127.0.0.1:8109/api/projects/fixture-project/graph",
            )
          ).json()
        ).nodes.length,
    )
    .toBe(52);
  await expect(
    page
      .getByRole("textbox", { name: "Node title" })
      .filter({ visible: true })
      .last(),
  ).toHaveValue("Untitled concept · copy");
});

test("home rename/delete and a new project's empty canvas are usable", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page.getByRole("textbox", { name: "Project name" }).fill("Desk forms");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Desk forms" })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "No projects yet" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "New Project", exact: true })
    .first()
    .click();
  await page.getByRole("button", { name: "Add your first node" }).click();
  await expect(
    page.getByRole("textbox", { name: "Design prompt" }),
  ).toHaveCount(1);
});

test("run progress survives reload and completion preserves the newer editable draft", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  const node = page.locator('.react-flow__node[data-id="target"]');
  const editor = node.getByRole("textbox", { name: "Design prompt" });
  await editor.fill("Frozen run instruction");
  await node.getByRole("button", { name: "Run", exact: true }).click();
  await expect(node.getByText(/Waiting for a worker/)).toBeVisible();
  await page.screenshot({ path: "../.progress/phase-f-canvas.png" });
  await page.reload();
  await expect(node.getByText(/Waiting for a worker/)).toBeVisible();
  await editor.fill("A newer draft during generation");
  await request.post("http://127.0.0.1:8109/finish-run");
  await expect(
    node.getByRole("button", { name: "Inspect active image" }),
  ).toBeVisible();
  await expect(editor).toHaveText("A newer draft during generation");
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  await page.reload();
  await expect(editor).toHaveText("A newer draft during generation");
  await node.getByRole("button", { name: "Run", exact: true }).click();
  await expect(node.getByText(/Waiting for a worker/)).toBeVisible();
  await request.post("http://127.0.0.1:8109/fail-run");
  await expect(node.getByRole("button", { name: "Retry run" })).toBeEnabled();
  await expect(editor).toHaveText("A newer draft during generation");
});

test("two tabs reject a stale save and let the user explicitly keep their draft", async ({
  page,
  context,
}) => {
  await page.goto("/projects/fixture-project");
  const second = await context.newPage();
  await second.goto("/projects/fixture-project");
  const firstEditor = page
    .locator('[data-id="target"]')
    .getByRole("textbox", { name: "Design prompt" });
  const secondEditor = second
    .locator('[data-id="target"]')
    .getByRole("textbox", { name: "Design prompt" });
  await firstEditor.fill("First tab draft");
  await secondEditor.fill("Second tab draft");
  await expect(second.getByText("Prompt changed in another tab")).toBeVisible();
  await expect(secondEditor).toHaveText("Second tab draft");
  await second.getByRole("button", { name: "Keep my draft" }).click();
  await expect(second.getByText("Saved", { exact: true })).toBeVisible();
  await second.reload();
  await expect(secondEditor).toHaveText("Second tab draft");
});

test("dependent deletion keeps a broken chip visible", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  const editor = page
    .locator('[data-id="target"]')
    .getByRole("textbox", { name: "Design prompt" });
  await editor.click();
  await editor.press("End");
  await editor.press("@");
  await page.getByRole("button", { name: "Desk lamp", exact: true }).click();
  await expect(editor.locator('[contenteditable="false"]')).toHaveText(
    "@Desk lamp",
  );
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .locator('[data-id="source"]')
    .getByRole("button", { name: "Delete node" })
    .click();
  await expect(editor.getByText("@Desk lamp")).toBeVisible();
  await expect(
    page
      .locator('[data-id="target"]')
      .getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
});

test("deleting an unsaved draft cancels its save and leaves no phantom changes", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  const target = page.locator('.react-flow__node[data-id="target"]');
  await target
    .getByRole("textbox", { name: "Design prompt" })
    .fill("Discard this draft");
  page.once("dialog", (dialog) => dialog.accept());
  await target.getByRole("button", { name: "Delete node" }).click();
  await expect(target).toHaveCount(0);
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
  // A stale pending-save entry would raise the unsaved-draft navigation confirmation.
  page.on("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "← Projects" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3009/");
});
