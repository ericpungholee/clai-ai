import { api, card, draft, graph, paint } from "./lifecycle-helpers";
import { test, expect } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  await request.post("http://127.0.0.1:8109/reset");
});

test("rectangle, brush, lasso, undo, empty selection and version binding", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await card(page, "target")
    .getByRole("button", { name: "Select area", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Save area selection", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("Select an area first");
  const canvas = dialog.locator("canvas");
  const box = (await canvas.boundingBox())!;
  for (const tool of ["rectangle", "brush", "lasso"]) {
    await dialog.getByRole("button", { name: tool, exact: true }).click();
    await page.mouse.move(box.x + 150, box.y + 110);
    await page.mouse.down();
    await page.mouse.move(box.x + 270, box.y + 110, { steps: 5 });
    await page.mouse.move(box.x + 270, box.y + 170, { steps: 5 });
    await page.mouse.move(box.x + 150, box.y + 170, { steps: 5 });
    await page.mouse.up();
    if (tool !== "lasso")
      await dialog.getByRole("button", { name: "Undo", exact: true }).click();
  }
  await dialog.getByLabel("Area to select").fill("nothing");
  await dialog.getByRole("button", { name: "Select", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("Nothing matched");
  await dialog
    .getByRole("button", { name: "Save area selection", exact: true })
    .click();
  await expect(dialog).not.toBeVisible();
  const graph = await (
    await request.get(
      "http://127.0.0.1:8109/api/projects/fixture-project/graph",
    )
  ).json();
  expect(graph.nodes[1].mask).toMatchObject({
    subject_version_id: "subject",
    width: 480,
    height: 360,
  });
  expect(graph.nodes[1].mask.rle).not.toBe("");
  await request.post("http://127.0.0.1:8109/stale");
  await page.reload();
  await expect(
    page.locator('[data-id="target"]').getByRole("alert"),
  ).toContainText("Area selection belongs to a different image");
  await expect(
    page
      .locator('[data-id="target"]')
      .getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
});

test("saving an area keeps the draft empty and prevents references", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await draft(page, "target").fill("");
  await card(page, "target")
    .getByRole("button", { name: "Select area", exact: true })
    .click();
  await paint(page);
  await page
    .getByRole("button", { name: "Save area selection", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(draft(page, "target")).toBeFocused();
  await expect(draft(page, "target")).toHaveAttribute(
    "data-placeholder",
    "Describe the change inside the selection…",
  );
  await expect(
    card(page, "target").getByText(
      "Area saved. Describe the change, then Run.",
    ),
  ).toBeVisible();
  await expect(card(page, "target").locator(".image-preview")).toHaveCount(0);
  await expect(
    card(page, "target").getByRole("button", {
      name: "Edit area",
      exact: true,
    }),
  ).toBeVisible();
  expect((await graph(request)).nodes[1].run).toBeNull();
  await draft(page, "target").press("@");
  const picker = page.getByRole("dialog", { name: "Add a reference" });
  await expect(picker).toContainText(
    "Area selections can't be combined with references. Remove the selection first.",
  );
  await expect(picker.getByRole("textbox")).toBeDisabled();
  await expect(picker.getByRole("button", { name: "Desk lamp" })).toHaveCount(
    0,
  );
  await picker.getByRole("button", { name: "Cancel" }).click();
  await draft(page, "target").fill("Make the shade orange");
  await expect(
    card(page, "target").getByText(
      "Area saved. Describe the change, then Run.",
    ),
  ).toHaveCount(0);
  await card(page, "target")
    .getByRole("button", { name: "Run", exact: true })
    .click();
  await expect(draft(page, "target")).toHaveAttribute(
    "contenteditable",
    "false",
  );
  await request.post(`${api}/finish-run`);
  await expect(
    card(page, "target").getByText("Outside the selection: unchanged."),
  ).toBeVisible();
  await expect(
    card(page, "target").getByLabel("Saved area selection"),
  ).toBeVisible();
});

test("references block area saving, and selection text counts while typing", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  await draft(page, "target").click();
  await draft(page, "target").press("@");
  await page.getByRole("button", { name: "Desk lamp", exact: true }).click();
  await card(page, "target")
    .getByRole("button", { name: "Select area", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(
    "This node has references. Remove them to save an area selection.",
  );
  await expect(
    dialog.getByRole("button", { name: "Save area selection" }),
  ).toBeDisabled();
  await dialog
    .getByRole("textbox", { name: "Area to select" })
    .fill("x".repeat(212));
  await expect(dialog.getByText("212 / 240")).toBeVisible();
  await dialog
    .getByRole("textbox", { name: "Area to select" })
    .fill("x".repeat(241));
  await expect(
    dialog.getByRole("button", { name: "Select", exact: true }),
  ).toBeDisabled();
});

test("whole-image selection explains its meaning while painting", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  await card(page, "target")
    .getByRole("button", { name: "Select area", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "brush", exact: true }).click();
  await dialog.getByRole("slider", { name: "Brush diameter" }).fill("160");
  const box = (await dialog.locator("canvas").boundingBox())!;
  await page.mouse.move(box.x + 1, box.y + 1);
  await page.mouse.down();
  for (let y = 0; y <= 4; y++) {
    await page.mouse.move(box.x + 1, box.y + Math.min(box.height - 1, y * 90), {
      steps: 3,
    });
    await page.mouse.move(
      box.x + box.width - 1,
      box.y + Math.min(box.height - 1, y * 90),
      { steps: 10 },
    );
  }
  // The explanation must appear before the pointer is released.
  await expect(
    dialog.getByText(
      "Selecting everything is the same as no selection — the run will edit the whole image.",
    ),
  ).toBeVisible();
  await page.mouse.up();
});
