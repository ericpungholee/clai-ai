import { expect, test } from "@playwright/test";
import { api, card, draft, graph } from "./lifecycle-helpers";

test.beforeEach(async ({ request }) => { await request.post(`${api}/reset`); });

test("white image and prompt surfaces, blank names, and useful input numbers", async ({ page, request }) => {
  await page.goto("/projects/fixture-project");
  for (const selector of [".image-preview", ".prompt-anchor", ".prompt-editor"]) {
    const colors = await page.locator(selector).evaluateAll(elements => elements.map(element => getComputedStyle(element).backgroundColor));
    expect(colors.length).toBeGreaterThan(0);
    expect(colors.every(color => color === "rgb(255, 255, 255)")).toBe(true);
  }
  await expect(card(page, "target").locator(".subject-number")).toHaveCount(0);
  await expect(card(page, "source").getByRole("group", { name: "Image view" })).toHaveCount(0);
  await card(page, "source").getByRole("button", { name: "New node" }).click();
  await expect.poll(async () => (await graph(request)).nodes.length).toBe(3);
  const child = (await graph(request)).nodes.at(-1);
  const title = card(page, child.id).getByRole("textbox", { name: "Node title" });
  await expect(title).toHaveValue("");
  await expect(title).toHaveAttribute("placeholder", "Name this node");
  await title.fill("My bottle");
  await expect.poll(async () => (await graph(request)).nodes.at(-1).title).toBe("My bottle");
  await title.fill("");
  await expect.poll(async () => (await graph(request)).nodes.at(-1).title).toBe("");
  await draft(page, child.id).fill("Change the cap");
  await card(page, child.id).getByRole("button", { name: "Run", exact: true }).click();
  await expect.poll(async () => (await graph(request)).nodes.at(-1).run?.status).toBe("queued");
  await expect(card(page, child.id).getByRole("button", { name: "White bg" })).toHaveCount(0);
  await expect(card(page, child.id).locator(".prompt-anchor")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await request.post(`${api}/finish-run`);
  await expect(card(page, child.id).getByRole("button", { name: "New node" })).toBeVisible();
  await expect(title).toHaveValue("");
  await expect(card(page, child.id).getByRole("button", { name: /Try another|Revise prompt/ })).toHaveCount(0);
});

test("New node inherits generation settings without exposing a toggle", async ({ page, request }) => {
  await page.goto("/projects/fixture-project");
  await card(page, "target").getByRole("button", { name: "Run", exact: true }).click();
  await expect.poll(async () => (await graph(request)).nodes[1].run?.status).toBe("queued");
  await request.post(`${api}/finish-run`);
  await card(page, "target").getByRole("button", { name: "New node" }).click();
  await expect.poll(async () => (await graph(request)).nodes.length).toBe(3);
  const child = (await graph(request)).nodes.at(-1);
  expect(child.settings.whiteBackground).toBe(true);
  await expect(card(page, child.id).getByRole("button", { name: "White bg" })).toHaveCount(0);
});
