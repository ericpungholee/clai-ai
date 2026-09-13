import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.image_views import mesh_view_urls
from app.models.graph import Version, VersionMesh
from app.providers.base import ArtifactReader, MeshProvider
from app.storage.artifacts import ArtifactStore
from app.storage.meshes import ingest_mesh


def execute_mesh_job(
    *,
    version_id: uuid.UUID,
    attempt_id: uuid.UUID,
    session_factory: sessionmaker[Session],
    provider: MeshProvider,
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
        front_url = mesh.source_artifact_url
        response_metadata = (
            version.provider_response_metadata if version is not None else None
        )
        texture = mesh.texture
    start = time.monotonic()
    try:
        source_views = mesh_view_urls(front_url=front_url, metadata=response_metadata)
        if not provider.supports_multiview:
            raise ValueError("This flow requires a multi-image reconstruction provider")
        # Persist the exact local inputs before uploading or submitting to TRELLIS.
        with session_factory.begin() as db:
            db.get(VersionMesh, version_id).provider_response_metadata = {
                "source_views": source_views,
                "input_policy": "stored_five_views",
            }
        source_urls = tuple(source_views.values())
        endpoint = provider.endpoint_for(source_urls)
        payload = provider.prepare(
            source_urls=source_urls, textured=texture == "standard"
        )
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.request_payload = payload
            mesh.model = endpoint
        provider_start = time.monotonic()
        request_id = provider.transport.submit(endpoint=endpoint, payload=payload)
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.provider_request_id = request_id
            mesh.status = "provider_pending"
        response = provider.transport.result(endpoint=endpoint, request_id=request_id)
        provider_elapsed = time.monotonic() - provider_start
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
                "source_views": source_views,
                "input_policy": "stored_five_views",
                "provider_elapsed_seconds": provider_elapsed,
                "preparation_elapsed_seconds": provider_start - start,
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
