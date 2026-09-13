import json
import logging
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO

import trimesh

from app.providers.base import ArtifactReader
from app.storage.artifacts import ArtifactStore, StoredArtifact, image_content_type

logger = logging.getLogger(__name__)


def validate_glb(content: bytes, *, require_texture: bool = False) -> None:
    if len(content) < 20:
        raise ValueError("The provider did not return a GLB mesh")
    magic, version, length, json_length, kind = struct.unpack_from("<4sIIII", content)
    if magic != b"glTF" or version != 2 or length != len(content) or kind != 0x4E4F534A:
        raise ValueError("The provider returned an invalid GLB mesh")
    if json_length % 4 or json_length > len(content) - 20:
        raise ValueError("The provider returned an invalid GLB JSON chunk")
    document = json.loads(content[20 : 20 + json_length])
    if not isinstance(document, dict):
        raise ValueError("The provider returned an invalid GLB document")
    for resource in [*document.get("buffers", []), *document.get("images", [])]:
        uri = resource.get("uri")
        if uri and not uri.startswith("data:"):
            raise ValueError(
                "The mesh contains an external asset instead of a self-contained GLB"
            )
    if require_texture:
        materials = document.get("materials", [])
        textures = document.get("textures", [])
        images = document.get("images", [])
        for mesh in document.get("meshes", []):
            for primitive in mesh.get("primitives", []):
                material_index = primitive.get("material")
                if not isinstance(material_index, int) or not (
                    0 <= material_index < len(materials)
                ):
                    continue
                color_texture = (
                    materials[material_index]
                    .get("pbrMetallicRoughness", {})
                    .get("baseColorTexture", {})
                )
                texture_index = color_texture.get("index")
                if not isinstance(texture_index, int) or not (
                    0 <= texture_index < len(textures)
                ):
                    continue
                image_index = _texture_source(textures[texture_index])
                if isinstance(image_index, int) and 0 <= image_index < len(images):
                    source = images[image_index]
                    if "bufferView" in source or source.get("uri", "").startswith(
                        "data:image/"
                    ):
                        return
        raise ValueError(
            "The provider returned a mesh without the image's color texture"
        )


def _texture_source(texture: object) -> object:
    if not isinstance(texture, dict):
        return None
    if "source" in texture:
        return texture["source"]
    extensions = texture.get("extensions")
    if not isinstance(extensions, dict):
        return None
    for name in ("EXT_texture_webp", "KHR_texture_basisu"):
        extension = extensions.get(name)
        if isinstance(extension, dict) and "source" in extension:
            return extension["source"]
    return None


@dataclass(frozen=True)
class StoredMesh:
    model: StoredArtifact
    preview: StoredArtifact | None


def ingest_mesh(
    *,
    response: dict[str, object],
    reader: ArtifactReader,
    store: ArtifactStore,
    attempt_id: str,
    textured: bool = True,
) -> StoredMesh:
    # Prefer the textured artifact when the provider also returns base geometry.
    mesh_keys = (
        ("model_glb", "pbr_model", "model_mesh")
        if textured
        else ("model_glb", "model_mesh", "base_model")
    )
    model_urls = response.get("model_urls")
    # Hunyuan's model_glb field can contain OBJ; use the explicit GLB entry first.
    mesh = model_urls.get("glb") if isinstance(model_urls, dict) else None
    if not mesh:
        mesh = next((response.get(key) for key in mesh_keys if response.get(key)), None)
    if not isinstance(mesh, dict) or not isinstance(mesh.get("url"), str):
        raise ValueError("The provider returned no mesh")
    content = reader.read(mesh["url"]).content
    if mesh.get("content_type") == "model/obj" or mesh["url"].split("?", 1)[0].endswith(
        ".obj"
    ):
        content = _obj_to_glb(content, response=response, reader=reader)
    validate_glb(content, require_texture=textured)
    artifact = store.put(
        key=f"meshes/{attempt_id}/model.glb",
        content=content,
        content_type="model/gltf-binary",
    )
    rendered = response.get("rendered_image") or response.get("thumbnail")
    preview = None
    if (
        isinstance(rendered, dict)
        and isinstance(rendered.get("url"), str)
        and rendered["url"]
    ):
        try:
            image = reader.read(rendered["url"])
            # fal can label valid WebP previews as application/octet-stream.
            content_type = image_content_type(image.content)
            suffix = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[
                content_type
            ]
            preview = store.put(
                key=f"meshes/{attempt_id}/preview.{suffix}",
                content=image.content,
                content_type=content_type,
            )
        except Exception:
            # A thumbnail failure must not discard the validated, paid GLB.
            logger.exception("Optional preview failed for mesh %s", attempt_id)
    return StoredMesh(model=artifact, preview=preview)


def _obj_to_glb(
    content: bytes, *, response: dict[str, object], reader: ArtifactReader
) -> bytes:
    resources = [response.get("material_mtl"), response.get("texture")]
    if any(
        not isinstance(resource, dict)
        or not isinstance(resource.get("url"), str)
        or not isinstance(resource.get("file_name"), str)
        for resource in resources
    ):
        raise ValueError("OBJ output requires its declared material and texture")

    def download(resource):
        data = reader.read(resource["url"]).content
        if resource is resources[1]:
            image_content_type(data)
        return resource["file_name"], data

    with ThreadPoolExecutor(max_workers=2) as pool:
        assets = dict(pool.map(download, resources))
    # Only declared, allowlisted downloads are visible to OBJ/MTL resolution.
    # Never resolve referenced filenames against the filesystem or the network.
    scene = trimesh.load_scene(
        BytesIO(content),
        file_type="obj",
        resolver=assets,
        allow_remote=False,
        process=False,
    )
    if not scene.geometry:
        raise ValueError("The provider returned an empty OBJ")
    for geometry in scene.geometry.values():
        material = getattr(geometry.visual, "material", None)
        if material is not None and hasattr(material, "to_pbr"):
            material = material.to_pbr()
            # OBJ diffuse textures are not metallic. glTF's omitted metallic
            # factor defaults to 1, which otherwise turns these exports black.
            material.metallicFactor = 0.0
            geometry.visual.material = material
    return trimesh.exchange.gltf.export_glb(scene)
