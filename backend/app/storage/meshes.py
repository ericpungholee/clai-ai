import json
import struct
from dataclasses import dataclass

from app.providers.base import ArtifactReader
from app.storage.artifacts import ArtifactStore, StoredArtifact, image_content_type


def validate_glb(content: bytes, *, require_texture: bool = False) -> None:
    if len(content) < 20:
        raise ValueError("The provider did not return a GLB mesh")
    magic, version, length, json_length, kind = struct.unpack_from("<4sIIII", content)
    if magic != b"glTF" or version != 2 or length != len(content) or kind != 0x4E4F534A:
        raise ValueError("The provider returned an invalid GLB mesh")
    document = json.loads(content[20 : 20 + json_length])
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
    mesh = next((response.get(key) for key in mesh_keys if response.get(key)), None)
    if not isinstance(mesh, dict) or not isinstance(mesh.get("url"), str):
        raise ValueError("The provider returned no mesh")
    content = reader.read(mesh["url"]).content
    validate_glb(content, require_texture=textured)
    artifact = store.put(
        key=f"meshes/{attempt_id}/model.glb",
        content=content,
        content_type="model/gltf-binary",
    )
    rendered = response.get("rendered_image")
    preview = None
    if (
        isinstance(rendered, dict)
        and isinstance(rendered.get("url"), str)
        and rendered["url"]
    ):
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
    return StoredMesh(model=artifact, preview=preview)
