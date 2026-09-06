import {
  ACESFilmicToneMapping,
  Box3,
  Color,
  DirectionalLight,
  Group,
  HemisphereLight,
  Matrix3,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  Quaternion,
  Raycaster,
  Scene,
  SRGBColorSpace,
  Texture,
  TextureLoader,
  Vector2,
  Vector3,
  WebGLRenderer,
  type Material,
  type Object3D,
} from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { decalOrientation, projectLogo } from "./decal-geometry";
import type { DecalPlacement, MeshDecal } from "./mesh-decals";

export type MeshScene = ReturnType<typeof createMeshScene>;

function disposeModel(root: Object3D) {
  const textures = new Set<Texture>();
  const materials = new Set<Material>();
  root.traverse((object) => {
    if (!(object instanceof Mesh)) return;
    object.geometry.dispose();
    for (const material of Array.isArray(object.material)
      ? object.material
      : [object.material]) {
      materials.add(material);
      for (const value of Object.values(material))
        if (value instanceof Texture) textures.add(value);
    }
  });
  for (const texture of textures) {
    texture.dispose();
    if (
      typeof ImageBitmap !== "undefined" &&
      texture.image instanceof ImageBitmap
    )
      texture.image.close();
  }
  for (const material of materials) material.dispose();
}

/** Imported only inside the mounted viewer's effect. No scene or WebGL on the server. */
export function createMeshScene(
  host: HTMLDivElement,
  url: string,
  callbacks: {
    loaded: () => void;
    error: (message: string) => void;
    placed: (placement: DecalPlacement) => void;
  },
) {
  const renderer = new WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  const canvas = renderer.domElement;
  canvas.setAttribute("aria-label", "Interactive 3D mesh");
  canvas.setAttribute("role", "img");
  canvas.tabIndex = 0;
  canvas.style.cssText =
    "width:100%;height:100%;display:block;touch-action:none";
  host.replaceChildren(canvas);
  const scene = new Scene();
  scene.background = new Color("#fafafa");
  scene.add(new HemisphereLight(0xffffff, 0x8c9199, 2.5));
  const light = new DirectionalLight(0xffffff, 3);
  light.position.set(3, 5, 4);
  scene.add(light);
  const fill = new DirectionalLight(0xffffff, 1);
  fill.position.set(-3, 1, -2);
  scene.add(fill);
  const camera = new PerspectiveCamera(35, 1, 0.01, 100);
  const controls = new OrbitControls(camera, canvas);
  // OrbitControls defaults allow continuous 360° rotation and top/bottom views.
  controls.enablePan = false;
  controls.minDistance = 0.8;
  controls.maxDistance = 8;
  const raycaster = new Raycaster();
  const meshes: Mesh[] = [];
  let model: Group | null = null;
  let disposed = false;
  let placing = false;
  let decal: MeshDecal | null = null;
  let decalMesh: Mesh | null = null;
  let texture: Texture | null = null;
  let textureUrl: string | null = null;
  let frame = 0;
  let fitted = false;
  let pointer: { id: number; x: number; y: number; moved: boolean } | null =
    null;
  const abort = new AbortController();

  function render() {
    if (disposed || frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!disposed) renderer.render(scene, camera);
    });
  }
  function resetCamera() {
    const distance =
      0.75 /
      Math.sin(
        Math.atan(
          Math.tan((camera.fov * Math.PI) / 360) * Math.min(1, camera.aspect),
        ),
      );
    controls.maxDistance = Math.max(8, distance * 2);
    camera.position.set(
      0,
      Math.cos((Math.PI * 5) / 12) * distance,
      Math.sin((Math.PI * 5) / 12) * distance,
    );
    controls.target.set(0, 0, 0);
    controls.update();
    render();
  }
  function resize() {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (!fitted) {
      resetCamera();
      fitted = true;
    }
    render();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(host);
  resize();
  controls.addEventListener("change", render);

  function clearDecal() {
    if (!decalMesh) return;
    scene.remove(decalMesh);
    decalMesh.geometry.dispose();
    (decalMesh.material as Material).dispose();
    decalMesh = null;
  }
  function rebuildDecal() {
    clearDecal();
    if (texture && decal?.placement && meshes[decal.placement.meshIndex]) {
      const geometry = projectLogo(meshes[decal.placement.meshIndex], decal);
      // Keep the original graphic's colors; model lighting must not wash out the logo.
      const material = new MeshBasicMaterial({
        map: texture,
        transparent: true,
        toneMapped: false,
        depthTest: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -4,
        polygonOffsetUnits: -4,
      });
      decalMesh = new Mesh(geometry, material);
      decalMesh.renderOrder = 1;
      scene.add(decalMesh);
    }
    render();
  }
  function setDecal(next: MeshDecal | null) {
    decal = next;
    const nextUrl = next?.crop.dataUrl ?? null;
    if (textureUrl !== nextUrl) {
      textureUrl = nextUrl;
      texture?.dispose();
      texture = null;
      if (nextUrl) {
        const pending = new TextureLoader().load(
          nextUrl,
          (loaded) => {
            if (disposed || textureUrl !== nextUrl) {
              loaded.dispose();
              return;
            }
            texture = loaded;
            rebuildDecal();
          },
          undefined,
          () => {
            if (!disposed && textureUrl === nextUrl)
              callbacks.error(
                "The logo texture could not load. Select it again.",
              );
          },
        );
        pending.colorSpace = SRGBColorSpace;
        pending.anisotropy = Math.min(
          8,
          renderer.capabilities.getMaxAnisotropy(),
        );
        texture = pending;
      }
    }
    rebuildDecal();
  }

  function pointerDown(event: PointerEvent) {
    if (event.isPrimary && event.button === 0)
      pointer = {
        id: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        moved: false,
      };
    else pointer = null;
  }
  function pointerMove(event: PointerEvent) {
    if (
      pointer &&
      Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > 5
    )
      pointer.moved = true;
  }
  function pointerUp(event: PointerEvent) {
    const start = pointer;
    pointer = null;
    if (
      !placing ||
      !start ||
      start.id !== event.pointerId ||
      start.moved ||
      !decal
    )
      return;
    const rect = canvas.getBoundingClientRect();
    camera.updateMatrixWorld();
    raycaster.setFromCamera(
      new Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      camera,
    );
    const hit = raycaster.intersectObjects(meshes, false)[0];
    if (!hit?.face) {
      callbacks.error("Click the model surface to place the logo.");
      return;
    }
    const mesh = hit.object as Mesh;
    const normal = (hit.normal ?? hit.face.normal)
      .clone()
      .applyNormalMatrix(new Matrix3().getNormalMatrix(mesh.matrixWorld));
    const up = new Vector3(0, 1, 0).applyQuaternion(
      camera.getWorldQuaternion(new Quaternion()),
    );
    callbacks.placed({
      meshIndex: meshes.indexOf(mesh),
      position: hit.point.toArray(),
      orientation: decalOrientation(normal, up),
    });
  }
  function cancelPointer() {
    pointer = null;
  }
  function contextLost(event: Event) {
    event.preventDefault();
    callbacks.error(
      "The browser lost its 3D context. Close and reopen this view to reload the model.",
    );
  }
  canvas.addEventListener("pointerdown", pointerDown);
  canvas.addEventListener("pointermove", pointerMove);
  canvas.addEventListener("pointerup", pointerUp);
  canvas.addEventListener("pointercancel", cancelPointer);
  canvas.addEventListener("webglcontextlost", contextLost);

  void (async () => {
    try {
      const response = await fetch(url, { signal: abort.signal });
      if (!response.ok) throw new Error("Mesh download failed");
      const gltf = await new GLTFLoader().parseAsync(
        await response.arrayBuffer(),
        "",
      );
      if (disposed) {
        disposeModel(gltf.scene);
        return;
      }
      model = new Group();
      model.add(gltf.scene);
      const bounds = new Box3().setFromObject(model);
      const size = bounds.getSize(new Vector3());
      const longest = Math.max(size.x, size.y, size.z);
      if (!Number.isFinite(longest) || longest <= 0)
        throw new Error("Empty mesh");
      model.scale.setScalar(1 / longest);
      model.position
        .copy(bounds.getCenter(new Vector3()))
        .multiplyScalar(-1 / longest);
      model.updateMatrixWorld(true);
      model.traverse((object) => {
        if (object instanceof Mesh) meshes.push(object);
      });
      if (!meshes.length) throw new Error("Empty mesh");
      scene.add(model);
      rebuildDecal();
      callbacks.loaded();
      render();
    } catch {
      if (!disposed)
        callbacks.error(
          "This browser could not display the mesh. Close and reopen to retry; the stored file is unchanged.",
        );
    }
  })();

  return {
    setDecal,
    setPlacing(value: boolean) {
      placing = value;
      canvas.style.cursor = value ? "crosshair" : "grab";
    },
    resetCamera,
    dispose() {
      disposed = true;
      abort.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("pointerdown", pointerDown);
      canvas.removeEventListener("pointermove", pointerMove);
      canvas.removeEventListener("pointerup", pointerUp);
      canvas.removeEventListener("pointercancel", cancelPointer);
      canvas.removeEventListener("webglcontextlost", contextLost);
      controls.dispose();
      clearDecal();
      texture?.dispose();
      if (model) disposeModel(model);
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}
