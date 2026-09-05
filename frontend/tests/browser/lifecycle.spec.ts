import { expect, test } from "@playwright/test";
import { api, nodeUrl, card, draft, graph } from "./lifecycle-helpers";
test.beforeEach(async ({ request }) => {
  await request.post(`${api}/reset`);
});

test("missing and deleted reference sources surface immediately with recovery", async ({
  page,
  request,
}) => {
  await request.post(nodeUrl, {
    data: { id: "empty", position: { x: 800, y: 0 } },
  });
  await page.goto("/projects/fixture-project");
  await draft(page, "target").click();
  await draft(page, "target").press("@");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Untitled node", exact: true })
    .click();
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "Reference has no image — run its source first.",
  );
  await expect(
    card(page, "target").getByRole("button", { name: "Find source" }),
  ).toBeVisible();
  await expect
    .poll(async () =>
      (await graph(request)).nodes[1].document.some(
        (part: { type: string }) => part.type === "connect",
      ),
    )
    .toBe(true);
  await request.delete(`${nodeUrl}/empty`);
  await page.reload();
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "Source deleted — remove or replace this reference.",
  );
  await card(page, "target")
    .getByRole("button", { name: "Remove reference" })
    .click();
  await expect(
    card(page, "target").getByRole("button", { name: "Run", exact: true }),
  ).toBeEnabled();
});

test("retained input and prompt length warnings are readable in the card", async ({
  page,
  request,
}) => {
  await request.delete(`${nodeUrl}/source`);
  await page.goto("/projects/fixture-project");
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "Source node deleted. This image is retained and still usable.",
  );
  await expect(
    card(page, "target").getByRole("button", {
      name: "Disconnect input",
      exact: true,
    }),
  ).toBeVisible();
  await draft(page, "target").fill("x".repeat(7832));
  await expect(card(page, "target").getByText("7,832 / 8,000")).toBeVisible();
  await draft(page, "target").fill("x".repeat(8001));
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "Prompt exceeds 8,000 characters.",
  );
  await expect(
    card(page, "target").getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
});

test("help contains the six invariants and shortcuts", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  await page.getByRole("button", { name: "Keyboard shortcuts" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.locator("li")).toHaveCount(6);
  await expect(dialog).toContainText("One node, one image.");
  await expect(dialog).toContainText(
    "Saving an area selection arms the node. Only Run generates.",
  );
  await expect(dialog.getByRole("table")).toContainText("Cmd/Ctrl+D");
});

test("a draft deleted remotely retains its unsaved text and cannot be saved back", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/nodes/target/prompt", async (route) => {
    await gate;
    await route.fulfill({ status: 404, json: { detail: "Node not found" } });
  });
  await draft(page, "target").fill("Keep these unsaved words");
  await request.delete(`${nodeUrl}/target`);
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "Node deleted — copy this text to a new node.",
    { timeout: 10000 },
  );
  await expect(draft(page, "target")).toHaveText("Keep these unsaved words");
  await expect(
    card(page, "target").getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
  await expect(
    card(page, "target").getByRole("button", {
      name: "Keep my draft",
      exact: true,
    }),
  ).toHaveCount(0);
  release();
});

test("a draft conflict can use the saved draft", async ({ page, request }) => {
  await page.goto("/projects/fixture-project");
  await request.put(`${nodeUrl}/target/prompt`, {
    data: {
      expected_revision: 0,
      document: [{ type: "text", text: "Saved elsewhere" }],
    },
  });
  await draft(page, "target").fill("Local words");
  await expect(card(page, "target").getByRole("alert")).toContainText(
    "changed in another tab",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await card(page, "target")
    .getByRole("button", { name: "Use saved draft", exact: true })
    .click();
  await expect(draft(page, "target")).toHaveText("Saved elsewhere");
  await expect(
    card(page, "target").getByRole("button", { name: "Run", exact: true }),
  ).toBeEnabled();
});
