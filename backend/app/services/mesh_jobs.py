import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.graph import VersionMesh
from app.providers.base import ArtifactReader
from app.providers.tripo import TRIPO_ENDPOINT, TripoProvider
from app.storage.artifacts import ArtifactStore
from app.storage.meshes import ingest_mesh


def execute_mesh_job(
    *,
    version_id: uuid.UUID,
    attempt_id: uuid.UUID,
    session_factory: sessionmaker[Session],
    provider: TripoProvider,
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
        source_url, texture = mesh.source_artifact_url, mesh.texture
    start = time.monotonic()
    try:
        if source_url is None:
            raise ValueError("This mesh job has no frozen input image")
        payload = provider.prepare(
            source_url=source_url, textured=texture == "standard"
        )
        with session_factory.begin() as db:
            db.get(VersionMesh, version_id).request_payload = payload
        request_id = provider.transport.submit(endpoint=TRIPO_ENDPOINT, payload=payload)
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.provider_request_id = request_id
            mesh.status = "provider_pending"
        response = provider.transport.result(
            endpoint=TRIPO_ENDPOINT, request_id=request_id
        )
        with session_factory.begin() as db:
            db.get(VersionMesh, version_id).status = "ingesting"
        stored = ingest_mesh(
            response=response,
            reader=output_reader,
            store=store,
            attempt_id=str(attempt_id),
        )
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.artifact_url = stored.model.artifact_url
            mesh.preview_url = stored.preview.artifact_url if stored.preview else None
            mesh.provider_response_metadata = {
                "task_id": response.get("task_id"),
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
