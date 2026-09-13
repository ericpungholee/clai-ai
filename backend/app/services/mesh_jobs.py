import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.graph import Version, VersionMesh
from app.providers.base import ArtifactReader
from app.providers.trellis import TRELLIS_ENDPOINT, TrellisProvider
from app.storage.artifacts import ArtifactStore
from app.storage.meshes import ingest_mesh


def execute_mesh_job(
    *,
    version_id: uuid.UUID,
    attempt_id: uuid.UUID,
    session_factory: sessionmaker[Session],
    provider: TrellisProvider,
    output_reader: ArtifactReader,
    store: ArtifactStore,
) -> None:
    with session_factory.begin() as db:
        mesh = db.scalar(
            select(VersionMesh)
            .where(VersionMesh.version_id == version_id)
            .with_for_update()
        )
        if mesh is None or mesh.attempt_id != attempt_id or mesh.status != "queued":
            return
        mesh.status = "dispatching"
        mesh.started_at = datetime.now(UTC)
        version = db.get(Version, version_id)
        front_url = version.artifact_url if version is not None else None
        response_metadata = (
            version.provider_response_metadata if version is not None else None
        )
        texture = mesh.texture
    start = time.monotonic()
    try:
        source_urls = _view_urls(
            front_url=front_url, response_metadata=response_metadata
        )
        payload = provider.prepare(source_urls=source_urls)
        with session_factory.begin() as db:
            db.get(VersionMesh, version_id).request_payload = payload
        request_id = provider.transport.submit(
            endpoint=TRELLIS_ENDPOINT, payload=payload
        )
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.provider_request_id = request_id
            mesh.status = "provider_pending"
        response = provider.transport.result(
            endpoint=TRELLIS_ENDPOINT, request_id=request_id
        )
        with session_factory.begin() as db:
            db.get(VersionMesh, version_id).status = "ingesting"
        stored = ingest_mesh(
            response=response,
            reader=output_reader,
            store=store,
            attempt_id=str(attempt_id),
            textured=texture == "standard",
        )
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.artifact_url = stored.model.artifact_url
            mesh.preview_url = stored.preview.artifact_url if stored.preview else None
            mesh.provider_response_metadata = {
                "timings": response.get("timings"),
                "artifact_sha256": stored.model.sha256,
                "artifact_storage_key": stored.model.storage_key,
                "byte_size": stored.model.byte_size,
            }
            mesh.status = "complete"
            mesh.elapsed_seconds = time.monotonic() - start
    except Exception as error:
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.status = "failed"
            mesh.error = (
                "The 3D view could not be created. Your image is unchanged. "
                f"{type(error).__name__}: {error}"
            )[:4000]
            mesh.elapsed_seconds = time.monotonic() - start
        raise


def _view_urls(
    *, front_url: str | None, response_metadata: dict[str, object] | None
) -> tuple[str, str, str, str]:
    if front_url is None:
        raise ValueError("Image version not found")
    views = response_metadata.get("views") if response_metadata is not None else None
    if not isinstance(views, dict):
        raise ValueError("This older image does not have multi-view data")
    ordered_urls = []
    for angle in ("front", "left", "back", "right"):
        url = front_url if angle == "front" else views.get(angle)
        if not isinstance(url, str) or not url:
            raise ValueError("This older image does not have multi-view data")
        ordered_urls.append(url)
    if views.get("front") != front_url:
        raise ValueError("This image has inconsistent multi-view data")
    return tuple(ordered_urls)
