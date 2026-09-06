import { expect, test } from "@playwright/test";
const api = "http://127.0.0.1:8109";
test.beforeEach(async ({ request }) => {
  await request.post(`${api}/reset`);
});
test("legacy images stay selectable without per-image mutation actions", async ({
  page,
  request,
}) => {
  await request.post(`${api}/many-versions`);
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await expect(
    source.getByText(
      "Older project — this node has 15 images. New nodes make one image each.",
    ),
  ).toHaveCount(0);
  await expect(
    source.getByRole("button", { name: "Select image 15", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await source
    .getByRole("button", { name: "Select image 1", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${api}/api/projects/fixture-project/graph`)
          ).json()
        ).nodes[0].active_version_id,
    )
    .toBe("subject");
  await source.getByRole("button", { name: "Inspect result" }).click();
  await expect(page.getByRole("dialog")).toContainText("Desk lamp");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("img")).toHaveCSS(
    "transform",
    /1.25/,
  );
  await page.keyboard.press("Escape");
  await expect(
    source.getByRole("button", { name: "Run", exact: true }),
  ).toHaveCount(0);
  await expect(
    source.getByRole("button", { name: /Hide|Restore|Compare|Branch/ }),
  ).toHaveCount(0);
});
test("result is a frozen picture with one way forward", async ({ page }) => {
  await page.goto("/projects/fixture-project");
  const source = page.locator('.react-flow__node[data-id="source"]');
  await expect(
    source.getByRole("textbox", { name: "Design prompt" }),
  ).toHaveAttribute("contenteditable", "false");
  await expect(source.getByLabel("Legacy images")).toHaveCount(0);
  await expect(
    source.getByRole("button", { name: "New node", exact: true }),
  ).toBeVisible();
  await expect(
    source.getByRole("button", { name: "White bg", exact: true }),
  ).toHaveCount(0);
  for (const name of ["Run", "Try another", "Revise prompt", "Select area"])
    await expect(source.getByRole("button", { name, exact: true })).toHaveCount(
      0,
    );
  await source.getByRole("textbox", { name: "Node title" }).fill("My lamp");
  await expect(source.getByRole("textbox", { name: "Node title" })).toHaveValue(
    "My lamp",
  );
});
