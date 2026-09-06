import { expect, test } from "@playwright/test";

test("record generate → continue editing → area selection → run", async ({
  browser,
  request,
}, testInfo) => {
  test.setTimeout(60000);
  const api = "http://127.0.0.1:8109";
  await request.post(`${api}/reset`);
  await request.post(`${api}/empty-projects`);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    recordVideo: {
      dir: testInfo.outputPath("video"),
      size: { width: 1440, height: 1000 },
    },
  });
  const page = await context.newPage();
  const start = Date.now();
  await page.goto("http://127.0.0.1:3009/");
  await page
    .getByRole("button", { name: "New Project", exact: true })
    .first()
    .click();
  await expect(page.getByRole("button", { name: "Add node", exact: true })).toBeVisible();
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: "Add node", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Design prompt" })
    .fill("A simple desk lamp");
  await page.waitForTimeout(1500);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Queued/)).toBeVisible();
  await page.waitForTimeout(2200);
  await request.post(`${api}/finish-run`);
  await page
    .getByRole("button", { name: "New node", exact: true })
    .click();
  const draft = page.locator('.design-card[data-state="draft"]');
  await expect(
    draft.getByRole("textbox", { name: "Design prompt" }),
  ).toBeFocused();
  await page.waitForTimeout(1500);
  await draft.getByRole("button", { name: "Select area", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "rectangle", exact: true }).click();
  const box = (await dialog.locator("canvas").boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.27, box.y + box.height * 0.25);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.73, box.y + box.height * 0.55, {
    steps: 30,
  });
  await page.mouse.up();
  await page.waitForTimeout(2000);
  await dialog
    .getByRole("button", { name: "Save area selection", exact: true })
    .click();
  await expect(
    draft.getByText("Area saved. Describe the change, then Run."),
  ).toBeVisible();
  await expect(
    draft.getByRole("textbox", { name: "Design prompt" }),
  ).toBeFocused();
  await page.waitForTimeout(2000);
  await draft
    .getByRole("textbox", { name: "Design prompt" })
    .pressSequentially("Make the shade orange", { delay: 70 });
  await page.waitForTimeout(1300);
  await draft.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByText(/Queued/)).toBeVisible();
  await page.waitForTimeout(2000);
  await request.post(`${api}/finish-run`);
  await expect(
    page.getByText("Outside the selection: unchanged."),
  ).toBeVisible();
  await page.getByRole("main").focus();
  await page.keyboard.press("f");
  await page.waitForTimeout(Math.max(1500, 30000 - (Date.now() - start)));
  await page.screenshot({ path: testInfo.outputPath("finished.png") });
  const video = page.video()!;
  await context.close();
  const destination = testInfo.outputPath("workflow.webm");
  await video.saveAs(destination);
  await testInfo.attach("30-second workflow (fixture provider)", {
    path: destination,
    contentType: "video/webm",
  });
});
