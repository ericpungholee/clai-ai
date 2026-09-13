import {
  Box3,
  BufferGeometry,
  Euler,
  Matrix3,
  Matrix4,
  Mesh,
  OrthographicCamera,
  Quaternion,
  Raycaster,
  Vector2,
  Vector3,
} from "three";
import { DecalGeometry } from "three/addons/geometries/DecalGeometry.js";
import type { DecalPlacement, MeshDecal } from "./mesh-decals";

/** Fit a fixed +Z front camera to the source subject, never the viewer viewport.
 * TRELLIS does not return camera calibration, so this assumes an upright front view.
 * Matching subject bounds compensates for source-image whitespace.
 */
export function autoPlaceLogo(meshes: Mesh[], decal: MeshDecal): MeshDecal | null {
  const subject = decal.source.subjectBounds;
  if (!subject || !meshes.length) return null;
  const bounds = new Box3();
  for (const mesh of meshes) bounds.union(new Box3().setFromObject(mesh));
  const extent = bounds.getSize(new Vector3());
  const width = extent.x / subject.width;
  const height = extent.y / subject.height;
  if (!(width > 0 && height > 0)) return null;
  const left = bounds.min.x - subject.x * width;
  const top = bounds.max.y + subject.y * height;
  const camera = new OrthographicCamera(
    left, left + width, top, top - height, 0.01, 10,
  );
  camera.position.set(0, 0, bounds.max.z + 2);
  camera.updateMatrixWorld(true);
  const crop = decal.source.bounds;
  const raycaster = new Raycaster();
  raycaster.setFromCamera(
    new Vector2(
      (crop.x + crop.width / 2) * 2 - 1,
      1 - (crop.y + crop.height / 2) * 2,
    ),
    camera,
  );
  const hit = raycaster.intersectObjects(meshes, false)[0];
  if (!hit?.face) return null;
  const mesh = hit.object as Mesh;
  const normal = (hit.normal ?? hit.face.normal)
    .clone()
    .applyNormalMatrix(new Matrix3().getNormalMatrix(mesh.matrixWorld));
  // A grazing side surface is not a trustworthy front-logo placement.
  if (normal.z < 0.4) return null;
  const size = Math.max(crop.width * width, crop.height * height);
  if (size <= 0 || size > 1) return null;
  return {
    ...decal,
    size,
    placement: {
      meshIndex: meshes.indexOf(mesh),
      position: hit.point.toArray(),
      orientation: decalOrientation(normal, new Vector3(0, 1, 0)),
    },
  };
}

export function decalOrientation(
  normal: Vector3,
  viewUp: Vector3,
): DecalPlacement["orientation"] {
  const z = normal.clone().normalize();
  const y = viewUp.clone().addScaledVector(z, -viewUp.dot(z));
  if (y.lengthSq() < 0.000001) {
    y.set(0, 0, -1).addScaledVector(z, z.z);
    if (y.lengthSq() < 0.000001) y.set(1, 0, 0);
  }
  y.normalize();
  const x = new Vector3().crossVectors(y, z).normalize();
  y.crossVectors(z, x);
  return new Quaternion()
    .setFromRotationMatrix(new Matrix4().makeBasis(x, y, z))
    .toArray();
}

/** DecalGeometry emits world-space triangles, so its output belongs at the scene root. */
export function projectLogo(mesh: Mesh, decal: MeshDecal) {
  const placement = decal.placement!;
  const orientation = new Quaternion()
    .fromArray(placement.orientation)
    .multiply(
      new Quaternion().setFromAxisAngle(
        new Vector3(0, 0, 1),
        (-decal.rotation * Math.PI) / 180,
      ),
    );
  const aspect = decal.crop.width / decal.crop.height;
  const width = decal.size * Math.min(1, aspect);
  const height = decal.size / Math.max(1, aspect);
  const position = new Vector3().fromArray(placement.position);
  // Reject distant triangles with a cheap bounds check before DecalGeometry allocates
  // clipping vertices on dense generated meshes.
  const toProjector = new Matrix4()
    .compose(position, orientation, new Vector3(1, 1, 1))
    .invert()
    .multiply(mesh.matrixWorld);
  const source = mesh.geometry.getAttribute("position");
  const sourceIndex = mesh.geometry.getIndex();
  const projected = new Float32Array(source.count * 3);
  const vertex = new Vector3();
  for (let i = 0; i < source.count; i++) {
    vertex
      .fromBufferAttribute(source, i)
      .applyMatrix4(toProjector)
      .toArray(projected, i * 3);
  }
  const candidates: number[] = [];
  const halfSize = [width / 2, height / 2, decal.size / 2];
  for (let i = 0; i < (sourceIndex?.count ?? source.count); i += 3) {
    const a = sourceIndex ? sourceIndex.getX(i) : i;
    const b = sourceIndex ? sourceIndex.getX(i + 1) : i + 1;
    const c = sourceIndex ? sourceIndex.getX(i + 2) : i + 2;
    if (
      halfSize.some(
        (half, axis) =>
          Math.min(
            projected[a * 3 + axis],
            projected[b * 3 + axis],
            projected[c * 3 + axis],
          ) >
            half + 1e-6 ||
          Math.max(
            projected[a * 3 + axis],
            projected[b * 3 + axis],
            projected[c * 3 + axis],
          ) <
            -half - 1e-6,
      )
    )
      continue;
    candidates.push(a, b, c);
  }
  const candidateGeometry = new BufferGeometry();
  candidateGeometry.setAttribute("position", source);
  if (mesh.geometry.getAttribute("normal"))
    candidateGeometry.setAttribute(
      "normal",
      mesh.geometry.getAttribute("normal"),
    );
  candidateGeometry.setIndex(candidates);
  const proxy = new Mesh(candidateGeometry, mesh.material);
  proxy.matrixWorld.copy(mesh.matrixWorld);
  const geometry = new DecalGeometry(
    proxy,
    position,
    new Euler().setFromQuaternion(orientation),
    new Vector3(width, height, decal.size),
  );
  candidateGeometry.dispose();
  // A projector can reach through a thin seat. Do not paint its opposing underside.
  const positions = geometry.getAttribute("position");
  const outward = new Vector3(0, 0, 1).applyQuaternion(orientation);
  const a = new Vector3(),
    b = new Vector3(),
    c = new Vector3();
  const indices: number[] = [];
  for (let i = 0; i < positions.count; i += 3) {
    a.fromBufferAttribute(positions, i);
    b.fromBufferAttribute(positions, i + 1).sub(a);
    c.fromBufferAttribute(positions, i + 2).sub(a);
    if (b.cross(c).dot(outward) >= 0) indices.push(i, i + 1, i + 2);
  }
  geometry.setIndex(indices);
  if (!geometry.getAttribute("normal")) geometry.computeVertexNormals();
  return geometry;
}
