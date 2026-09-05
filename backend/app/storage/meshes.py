import json
import struct
from dataclasses import dataclass

from app.providers.base import ArtifactReader
from app.storage.artifacts import ArtifactStore, StoredArtifact


def validate_glb(content: bytes) -> None:
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
) -> StoredMesh:
    mesh = response.get("model_mesh")
    if not isinstance(mesh, dict) or not isinstance(mesh.get("url"), str):
        raise ValueError("The provider returned no mesh")
    content = reader.read(mesh["url"]).content
    validate_glb(content)
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
        if image.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ValueError("The provider preview is not a supported image")
        suffix = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[
            image.content_type
        ]
        preview = store.put(
            key=f"meshes/{attempt_id}/preview.{suffix}",
            content=image.content,
            content_type=image.content_type,
        )
    return StoredMesh(model=artifact, preview=preview)
