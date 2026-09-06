import { api, nodeUrl, card, draft, graph } from "./lifecycle-helpers";
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
  await expect(
    page.getByRole("main", { name: "Project graph workspace" }),
  ).toBeFocused();
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
  ).toHaveValue("");
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
  ).toHaveValue("");
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
  await page.getByRole("button", { name: "Add node" }).click();
  await expect(
    page.getByRole("textbox", { name: "Design prompt" }),
  ).toHaveCount(1);
  await expect(
    page.getByRole("textbox", { name: "Design prompt" }),
  ).toHaveAttribute("data-placeholder", "Describe a design…");
  await expect(page.getByText("Enter a prompt.", { exact: true })).toHaveCount(
    0,
  );
  const viewport = page.locator(".react-flow__viewport");
  const beforePan = await viewport.getAttribute("style");
  const pane = (await page.locator(".react-flow__pane").boundingBox())!;
  await page.mouse.move(pane.x + pane.width - 100, pane.y + pane.height - 100);
  await page.mouse.down();
  await page.mouse.move(pane.x + pane.width - 200, pane.y + pane.height - 180);
  await page.mouse.up();
  await expect(viewport).not.toHaveAttribute("style", beforePan!);
});

test("running locks a draft, success freezes it, and failure allows retry", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  const node = page.locator('.react-flow__node[data-id="target"]');
  const editor = node.getByRole("textbox", { name: "Design prompt" });
  await editor.fill("Frozen run instruction");
  await node.getByRole("button", { name: "Run", exact: true }).click();
  await expect(editor).toHaveAttribute("contenteditable", "false");
  await page.reload();
  await expect(editor).toHaveAttribute("contenteditable", "false");
  await request.post("http://127.0.0.1:8109/fail-run");
  await expect(editor).toHaveAttribute("contenteditable", "true");
  await editor.fill("A corrected instruction");
  await node.getByRole("button", { name: "Retry", exact: true }).click();
  await request.post("http://127.0.0.1:8109/finish-run");
  await expect(
    node.getByRole("button", { name: "New node" }),
  ).toBeVisible();
  await expect(editor).toHaveText("A corrected instruction");
  await expect(editor).toHaveAttribute("contenteditable", "false");
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
  await expect(
    second.locator('[data-id="target"]').getByRole("alert"),
  ).toContainText("changed in another tab");
  await expect(
    second.getByText("Prompt changed in another tab").filter({ visible: true }),
  ).toBeVisible();
  await expect(secondEditor).toHaveText("Second tab draft");
  await second.getByRole("button", { name: "Keep my draft" }).click();
  await expect(
    second.getByRole("status", { name: "Saved", exact: true }).first(),
  ).toBeVisible();
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
    "2@Desk lamp",
  );
  await expect(
    page.getByRole("status", { name: "Saved", exact: true }).first(),
  ).toBeVisible();
  await page
    .locator('[data-id="source"]')
    .getByRole("button", { name: "Node actions" })
    .click();
  await page.getByRole("button", { name: "Delete node" }).click();
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Cancel" }),
  ).toBeFocused();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete node" })
    .click();
  await expect(
    editor.getByRole("button", { name: "Image 2: Desk lamp" }),
  ).toBeVisible();
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
  await target.getByRole("button", { name: "Node actions" }).click();
  await page.getByRole("button", { name: "Delete node", exact: true }).click();
  const confirmation = page.getByRole("dialog");
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Delete node" }).click();
  await expect(target).toHaveCount(0);
  await expect(
    page.getByRole("status", { name: "Saved", exact: true }).first(),
  ).toBeVisible();
  // A stale pending-save entry would raise the unsaved-draft navigation confirmation.
  page.on("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "← Projects" }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3009/");
});

test("New node creates a connected draft and focuses it", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await card(page, "source")
    .getByRole("button", { name: "New node", exact: true })
    .click();
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  const state = await graph(request);
  const continued = state.nodes.at(-1);
  expect(continued.position.x).toBeGreaterThan(state.nodes[0].position.x);
  expect(continued.position.y).toBe(state.nodes[0].position.y);
  expect(continued.prompt).toBe("");
  expect(continued.run).toBeNull();
  expect(
    state.edges.find(
      (edge: { target_node_id: string }) =>
        edge.target_node_id === continued.id,
    ).pin.version_id,
  ).toBe("subject");
  await expect(draft(page, continued.id)).toBeFocused();
  await expect(card(page, continued.id).locator(".image-preview")).toHaveCount(
    0,
  );
  await expect(
    card(page, continued.id).getByRole("button", { name: "White bg" }),
  ).toHaveCount(0);
  await expect(
    card(page, continued.id).getByRole("button", {
      name: "Inspect Desk lamp",
    }),
  ).toBeVisible();

  await expect(card(page, "source").getByRole("button", { name: /Try another|Revise prompt/ })).toHaveCount(0);
});

test("canvas comparison appears only for exactly two image nodes", async ({
  page,
  request,
}) => {
  await request.post(`${nodeUrl}/target/runs`, {
    data: { idempotency_key: "second-image" },
  });
  await request.post(`${api}/finish-run`);
  await page.goto("/projects/fixture-project");
  await card(page, "source").click({ position: { x: 2, y: 40 } });
  await expect(
    page.getByRole("button", { name: "Compare", exact: true }),
  ).toHaveCount(0);
  await page.keyboard.down("Shift");
  await card(page, "target").click({ position: { x: 2, y: 40 } });
  await page.keyboard.up("Shift");
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("img")).toHaveCount(2);
  await expect(page.getByRole("dialog")).toContainText("Desk lamp");
  await expect(page.getByRole("dialog")).not.toContainText("Before");
  await page.keyboard.press("Escape");
  await request.post(nodeUrl, {
    data: { id: "third", position: { x: 0, y: 850 } },
  });
  await page.reload();
  for (const id of ["source", "target", "third"]) {
    await page.keyboard.down("Shift");
    await card(page, id).click({ position: { x: 2, y: 40 } });
    await page.keyboard.up("Shift");
  }
  await expect(
    page.getByRole("button", { name: "Compare", exact: true }),
  ).toHaveCount(0);
});

test("ten continued images form a row and F frames the whole chain", async ({
  page,
  request,
}) => {
  test.setTimeout(60000);
  // Start with a single result so the spatial grammar is unambiguous.
  await request.delete(`${nodeUrl}/target`);
  await page.goto("/projects/fixture-project");
  let id = "source";
  const positions = [(await graph(request)).nodes[0].position];
  for (let i = 1; i < 10; i++) {
    await card(page, id)
      .getByRole("button", { name: "New node", exact: true })
      .click();
    await expect
      .poll(async () => (await graph(request)).nodes.length)
      .toBe(i + 2);
    const child = (await graph(request)).nodes.at(-1);
    positions.push(child.position);
    id = child.id;
    await expect(draft(page, id)).toBeFocused();
    await draft(page, id).fill(`Change feature ${i}`);
    await card(page, id)
      .getByRole("button", { name: "Run", exact: true })
      .click();
    await expect
      .poll(async () => (await graph(request)).nodes.at(-1).run?.status)
      .toBe("queued");
    await request.post(`${api}/finish-run`);
    await expect(
      card(page, id).getByRole("button", { name: "New node" }),
    ).toBeVisible();
  }
  for (let i = 1; i < positions.length; i++) {
    expect(positions[i].x).toBeGreaterThan(positions[i - 1].x);
    expect(positions[i].y).toBe(positions[0].y);
  }
  await page.getByRole("main").focus();
  await page.keyboard.press("f");
  await expect(card(page, "source")).toBeInViewport();
  await expect(card(page, id)).toBeInViewport();
});
