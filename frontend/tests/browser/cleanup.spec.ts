import {
  expect,
  test,
  type Page,
  type APIRequestContext,
} from "@playwright/test";

const api = "http://127.0.0.1:8109";
const graphUrl = `${api}/api/projects/fixture-project/graph`;
const nodeUrl = `${api}/api/projects/fixture-project/nodes/target`;
const node = (page: Page, id = "target") =>
  page.locator(`.react-flow__node[data-id="${id}"]`);
async function reference(request: APIRequestContext) {
  await request.put(`${nodeUrl}/prompt`, {
    data: {
      expected_revision: 0,
      document: [
        { type: "connect", edge_id: "reference", source_node_id: "source" },
        { type: "text", text: ". Keep the proportions." },
      ],
    },
  });
}
async function menu(page: Page, id: string, action: string) {
  await node(page, id)
    .getByRole("button", { name: "Node actions", exact: true })
    .click();
  await page.getByRole("button", { name: action, exact: true }).click();
}
test.beforeEach(async ({ request }) => {
  await request.post(`${api}/reset`);
});

test("wire roles use separate endpoints, shapes, numbers and linked hover", async ({
  page,
  request,
}) => {
  await reference(request);
  await page.goto("/projects/fixture-project");
  const subject = page.locator('.react-flow__edge[data-id="wire"]');
  const ref = page.locator('.react-flow__edge[data-id="reference"]');
  await expect(subject).toBeVisible();
  await expect(ref).toBeVisible();
  await expect(node(page).locator(".subject-dock")).toHaveCSS("height", "24px");
  for (const id of ["source"]) {
    const metrics = await node(page, id).evaluate((element) => {
      const card = element
        .querySelector(".design-card")!
        .getBoundingClientRect();
      const side =
        element.getAttribute("data-id") === "source" ? ".source" : ".target";
      return ["subject", "reference"].map((role) => {
        const handle = element
          .querySelector(`.wire-${role}${side}`)!
          .getBoundingClientRect();
        return (handle.y + handle.height / 2 - card.y) / card.height;
      });
    });
    expect(metrics[0]).toBeCloseTo(0.35, 2);
    expect(metrics[1]).toBeCloseTo(0.7, 2);
  }
  const anchors = await node(page).evaluate((element) => {
    const center = (selector: string) => {
      const rect = element.querySelector(selector)!.getBoundingClientRect();
      return rect.y + rect.height / 2;
    };
    return {
      subject: center(".wire-subject.target"),
      chip: center(".subject-chip"),
      reference: center(".wire-reference.target"),
      prompt: center(".prompt-anchor"),
    };
  });
  expect(anchors.subject).toBeCloseTo(anchors.chip, 0);
  expect(anchors.reference).toBeCloseTo(anchors.prompt, 0);
  expect(anchors.subject).toBeLessThan(anchors.reference);
  await expect(subject.locator(".react-flow__edge-path")).toHaveCSS(
    "stroke-width",
    "2.5px",
  );
  await expect(ref.locator(".react-flow__edge-path")).toHaveCSS(
    "stroke-dasharray",
    "6px, 4px",
  );
  await expect(page.locator('[data-wire-id="wire"]')).toHaveText("1×");
  await expect(page.locator('[data-wire-id="reference"]')).toHaveAttribute(
    "data-number",
    "2",
  );
  const chip = node(page).getByRole("button", { name: "Image 2: Desk lamp" });
  await chip.hover();
  await expect(ref.locator(".react-flow__edge-path")).toHaveCSS(
    "stroke-width",
    "3.5px",
  );
  await expect(subject.locator("g").first()).toHaveCSS("opacity", "0.25");
  await page.locator('[data-wire-id="reference"]').hover();
  await expect(chip).toHaveAttribute("data-highlighted", "true");
  for (const id of ["source", "target"]) {
    await expect(node(page, id).locator(".design-card")).toHaveAttribute(
      "data-wire-highlighted",
      "true",
    );
    await expect(node(page, id)).toHaveCSS("outline-style", "none");
    await expect(node(page, id).locator(".design-card")).toHaveCSS(
      "border-color",
      "rgb(212, 212, 212)",
    );
  }
  await expect(node(page, "source").locator(".design-card")).toHaveAttribute(
    "data-kind",
    "origin",
  );
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "edit",
  );
});

test("removing a reference updates the document and renumbers before autosave", async ({
  page,
  request,
}) => {
  await request.post(`${api}/api/projects/fixture-project/nodes`, {
    data: { id: "second", position: { x: 800, y: 0 } },
  });
  await request.put(`${nodeUrl}/prompt`, {
    data: {
      expected_revision: 0,
      document: [
        { type: "connect", edge_id: "reference", source_node_id: "source" },
        { type: "text", text: " and " },
        { type: "connect", edge_id: "second-ref", source_node_id: "second" },
      ],
    },
  });
  await page.goto("/projects/fixture-project");
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/nodes/target/prompt", async (route) => {
    await gate;
    await route.continue();
  });
  await page.locator('[data-wire-id="reference"]').click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(node(page).locator('[data-edge-id="reference"]')).toHaveCount(0);
  await expect(page.locator('[data-wire-id="reference"]')).toHaveCount(0);
  await expect(page.locator('[data-wire-id="second-ref"]')).toHaveAttribute(
    "data-number",
    "2",
  );
  await expect(
    node(page).getByRole("button", { name: "Image 2: Image" }),
  ).toBeVisible();
  expect(
    (await (await request.get(graphUrl)).json()).nodes[1].document.filter(
      (part: { type: string }) => part.type === "connect",
    ),
  ).toHaveLength(2);
  release();
  await expect
    .poll(
      async () =>
        (await (await request.get(graphUrl)).json()).nodes[1].document.filter(
          (part: { type: string }) => part.type === "connect",
        ).length,
    )
    .toBe(1);
});

test("disconnect confirms a saved mask, clears it and changes to origin", async ({
  page,
  request,
}) => {
  await request.put(`${nodeUrl}/mask`, {
    data: {
      rle: "1 600",
      width: 480,
      height: 360,
      subject_version_id: "subject",
    },
  });
  await page.goto("/projects/fixture-project");
  await page.locator('[data-wire-id="wire"]').click();
  await expect(page.getByRole("dialog")).toHaveText(
    "Disconnect input? The saved area selection will be cleared.CancelDisconnect",
  );
  await expect(
    page.getByRole("button", { name: "Cancel", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "edit",
  );
  await page.locator('[data-wire-id="wire"]').click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Disconnect", exact: true })
    .click();
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "origin",
  );
  await expect(
    node(page).getByRole("button", { name: "White bg" }),
  ).toHaveCount(0);
  await expect(
    node(page).getByRole("button", { name: "Edit area" }),
  ).toHaveCount(0);
  await expect
    .poll(
      async () => (await (await request.get(graphUrl)).json()).nodes[1].mask,
    )
    .toBeNull();
  await expect
    .poll(async () => (await (await request.get(graphUrl)).json()).edges.length)
    .toBe(0);
  await page.reload();
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "origin",
  );
});

test("deleting a source keeps pinned images runnable and breaks only references", async ({
  page,
  request,
}) => {
  await reference(request);
  await page.goto("/projects/fixture-project");
  await menu(page, "source", "Delete node");
  await expect(page.getByRole("dialog")).toContainText(
    'Delete "Desk lamp"? Its 1 image stays available to the 1 node using them.',
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete node" })
    .click();
  await expect(node(page, "source")).toHaveCount(0);
  await expect(node(page).locator(".subject-chip")).toHaveCSS("opacity", "0.5");
  await expect(
    page.locator('[data-wire-id="reference"] .badge-number'),
  ).toHaveText("!");
  await expect(
    node(page).getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
  await page.locator('[data-wire-id="reference"]').click();
  await expect(
    node(page).getByRole("button", { name: "Run", exact: true }),
  ).toBeEnabled();
  await node(page).getByRole("button", { name: "Run", exact: true }).click();
  await expect(
    node(page).getByRole("status").filter({ hasText: "Queued" }),
  ).toBeVisible();
  await page.reload();
  await expect(node(page, "source")).toHaveCount(0);
  await expect(node(page).locator(".subject-chip")).toHaveCSS("opacity", "0.5");
});

test("deletion keys are suppressed in editors and image dialogs", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  await node(page, "source")
    .getByRole("textbox", { name: "Node title" })
    .click();
  await page.keyboard.press("Backspace");
  await expect(node(page, "source")).toHaveCount(1);
  await node(page, "source")
    .getByRole("button", { name: "Inspect result" })
    .click();
  await page.keyboard.press("Delete");
  await expect(node(page, "source")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("maskless disconnect and an unused empty node delete without confirmation", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  await page.locator('[data-wire-id="wire"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "origin",
  );
  await menu(page, "target", "Delete node");
  await expect(node(page)).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await menu(page, "source", "Delete node");
  await expect(page.getByRole("dialog")).toContainText(
    'Delete "Desk lamp"? Its 1 image will no longer appear on the canvas.',
  );
  await expect(
    page.getByRole("dialog").getByRole("button", { name: "Cancel" }),
  ).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(node(page, "source")).toHaveCount(1);
});

test("handles connect by keyboard and switch origin into edit", async ({
  page,
}) => {
  await page.goto("/projects/fixture-project");
  await page.locator('[data-wire-id="wire"]').click();
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "origin",
  );
  await node(page, "source")
    .getByRole("button", { name: "Start input image" })
    .focus();
  await page.keyboard.press("Enter");
  await node(page).getByRole("button", { name: "Add input image" }).focus();
  await page.keyboard.press("Enter");
  await expect(node(page).locator(".design-card")).toHaveAttribute(
    "data-kind",
    "edit",
  );
  await expect(
    node(page).getByRole("button", { name: "White bg" }),
  ).toHaveCount(0);
  await node(page, "source").hover();
  await node(page, "source")
    .getByRole("button", { name: "Start input image" })
    .dragTo(node(page).getByRole("button", { name: "Add input image" }));
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  await node(page, "source").hover();
  await node(page, "source")
    .getByRole("button", { name: "Start reference" })
    .dragTo(node(page).getByRole("button", { name: "Add reference" }));
  await expect(page.locator(".react-flow__edge")).toHaveCount(2);
  await expect(
    node(page).getByRole("button", { name: "Image 2: Desk lamp" }),
  ).toBeVisible();
});

test("multi-select deletes once and in-flight runs keep their frozen job", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await node(page).getByRole("button", { name: "Run", exact: true }).click();
  await expect(
    node(page).getByRole("status").filter({ hasText: "Queued" }),
  ).toBeVisible();
  const before = (await (await request.get(graphUrl)).json()).nodes[1].run;
  await node(page, "source").click({ position: { x: 80, y: 5 } });
  await page.keyboard.down("Shift");
  await node(page).click({ position: { x: 80, y: 5 } });
  await page.keyboard.up("Shift");
  await page.keyboard.press("Delete");
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toContainText(
    "Delete 2 nodes and 0 wires?",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.locator(".react-flow__node")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const after = (await (await request.get(graphUrl)).json()).nodes[1].run;
  expect(after).toEqual(before);
  await request.post(`${api}/finish-run`);
  await expect
    .poll(
      async () =>
        (await (await request.get(graphUrl)).json()).nodes[1].run.status,
    )
    .toBe("complete");
});

test("a stale selection uses the fixed warning slot", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  await expect(node(page).locator(".subject-dock")).toHaveCSS("height", "24px");
  const before = (await node(page).boundingBox())!.height;
  await request.put(`${nodeUrl}/mask`, {
    data: {
      rle: "1 600",
      width: 480,
      height: 360,
      subject_version_id: "stale",
    },
  });
  await page.reload();
  await expect(node(page).locator(".subject-dock")).toHaveCSS("height", "24px");
  await expect(node(page).getByRole("alert")).toHaveCount(1);
  await expect(node(page).getByRole("alert")).toContainText(
    "Area selection belongs to a different image",
  );
  await expect(
    node(page).getByRole("button", { name: "Run", exact: true }),
  ).toBeDisabled();
  expect((await node(page).boundingBox())!.height - before).toBeLessThanOrEqual(
    28,
  );
});

test("deleting during an autosave removes the card immediately and serializes its request", async ({
  page,
  request,
}) => {
  await page.goto("/projects/fixture-project");
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  let started!: () => void;
  const saving = new Promise<void>((resolve) => {
    started = resolve;
  });
  await page.route("**/nodes/target/prompt", async (route) => {
    started();
    await gate;
    await route.continue();
  });
  await node(page)
    .getByRole("textbox", { name: "Design prompt" })
    .fill("A pending saved draft");
  await saving;
  await menu(page, "target", "Delete node");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete node" })
    .click();
  await expect(node(page)).toHaveCount(0);
  expect((await (await request.get(graphUrl)).json()).nodes[1].deleted).toBe(
    false,
  );
  release();
  await expect
    .poll(
      async () => (await (await request.get(graphUrl)).json()).nodes[1].deleted,
    )
    .toBe(true);
  await page.reload();
  await expect(node(page)).toHaveCount(0);
});
