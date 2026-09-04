import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { decodeMask, encodeMask } from "../lib/mask-rle.ts";

test("browser encoder matches the captured SAM response without transposing it", () => {
  const fixture = JSON.parse(
    readFileSync(
      new URL(
        "../../backend/tests/fixtures/sam-3-image-rle.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const rle: string = fixture.response.rle[0];
  const pixels = decodeMask(rle, fixture.width, fixture.height);
  assert.equal(pixels[(214 * 1280 + 448) * 4 + 3], 255);
  assert.equal(pixels[(214 * 1280 + 447) * 4 + 3], 0);
  assert.equal(encodeMask(pixels).rle, rle);
});

test("empty, full, disjoint and out-of-bounds masks", () => {
  assert.deepEqual(encodeMask(decodeMask("", 2, 3)), { rle: "", count: 0 });
  assert.deepEqual(encodeMask(decodeMask("1 6", 2, 3)), {
    rle: "1 6",
    count: 6,
  });
  assert.equal(encodeMask(decodeMask("1 1 6 1", 2, 3)).count, 2);
  assert.throws(() => decodeMask("6 2", 2, 3));
  assert.throws(() => decodeMask("1 3 2 1", 2, 3));
});
