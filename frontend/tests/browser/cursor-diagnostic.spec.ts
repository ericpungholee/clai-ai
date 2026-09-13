import { expect, test } from "@playwright/test";

test("browser cursor annotations reproduce the hydration warning", async ({ page, request }) => {
  await request.post("http://127.0.0.1:8109/reset");
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  // Model an inspection tool mutating the parsed DOM before React hydrates it.
  await page.addInitScript(() => {
    const observer = new MutationObserver(() => {
      const heading = document.querySelector("h1");
      const main = document.querySelector("main");
      heading?.setAttribute("data-cursor-ref", "e2");
      main?.setAttribute("data-cursor-ref", "e3");
      if (heading && main) observer.disconnect();
    });
    observer.observe(document, { subtree: true, childList: true });
  });
  await page.goto("/projects/fixture-project");
  await expect.poll(() => errors.some((error) => /hydrat/i.test(error))).toBe(true);
  expect(errors.some((error) => error.includes("data-cursor-ref"))).toBe(true);
});
