import type { Page, APIRequestContext } from "@playwright/test";
export const api = "http://127.0.0.1:8109";
const graphUrl = `${api}/api/projects/fixture-project/graph`;
export const nodeUrl = `${api}/api/projects/fixture-project/nodes`;
export const card = (page: Page, id: string) =>
  page.locator(`.react-flow__node[data-id="${id}"]`);
export const graph = async (request: APIRequestContext) =>
  (await request.get(graphUrl)).json();
export const draft = (page: Page, id: string) =>
  card(page, id).getByRole("textbox", { name: "Design prompt" });
export async function paint(page: Page) {
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "rectangle", exact: true }).click();
  const box = (await dialog.locator("canvas").boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6, {
    steps: 6,
  });
  await page.mouse.up();
}
