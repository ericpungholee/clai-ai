import assert from "node:assert/strict";
import test from "node:test";
import { BoxGeometry, Mesh, MeshBasicMaterial, Quaternion, Vector3 } from "three";
import { autoPlaceLogo, projectLogo } from "../lib/decal-geometry.ts";
import type { MeshDecal } from "../lib/mesh-decals.ts";

function fixture(): { mesh: Mesh; decal: MeshDecal } {
  const mesh = new Mesh(new BoxGeometry(0.6, 1, 0.3), new MeshBasicMaterial());
  mesh.updateMatrixWorld(true);
  return { mesh, decal: {
    crop: { dataUrl: "https://clai.test/logo.png", width: 100, height: 100 },
    source: {
      url: "https://clai.test/source.png", mode: "auto",
      subjectBounds: { x: 0.2, y: 0.1, width: 0.6, height: 0.8 },
      bounds: { x: 0.45, y: 0.4, width: 0.1, height: 0.1 },
    },
    placement: null, size: 0.25, rotation: 0,
  } };
}

test("front placement compensates for framing and creates outward-facing decal triangles", () => {
  const { mesh, decal } = fixture();
  const placed = autoPlaceLogo([mesh], decal)!;
  assert.ok(placed?.placement);
  const [x, y, z] = placed.placement.position;
  assert.ok(Math.abs(x) < 1e-6);
  assert.ok(Math.abs(y - 0.0625) < 1e-6);
  assert.ok(Math.abs(z - 0.15) < 1e-6);
  assert.ok(Math.abs(placed.size - 0.125) < 1e-6);
  const outward = new Vector3(0, 0, 1).applyQuaternion(new Quaternion().fromArray(placed.placement.orientation));
  assert.ok(outward.z > 0.99);
  const geometry = projectLogo(mesh, placed);
  assert.ok(geometry.index!.count > 0);
  const positions = geometry.getAttribute("position");
  for (let i = 0; i < positions.count; i++) assert.ok(positions.getZ(i) > 0);
  assert.deepEqual(autoPlaceLogo([mesh], decal), placed);
  geometry.dispose();
});

test("missing foreground calibration or a missed ray leaves placement manual", () => {
  const { mesh, decal } = fixture();
  decal.source.bounds.x = 0.9;
  assert.equal(autoPlaceLogo([mesh], decal), null);
  decal.source.subjectBounds = null;
  assert.equal(autoPlaceLogo([mesh], decal), null);
});
