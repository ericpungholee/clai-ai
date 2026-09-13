import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.graph import VersionMesh
from app.providers.base import ArtifactReader
from app.providers.mesh import (
    TRELLIS_ENDPOINT,
    MeshProvider,
    recoverable_mesh_response,
    snapshot_mesh_response,
)
from app.providers.tripo import PreparedMeshRequest
from app.storage.artifacts import ArtifactStore
from app.storage.meshes import ingest_mesh

logger = logging.getLogger(__name__)


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
        source_url, image_urls, texture, saved_response = (
            mesh.source_artifact_url,
            list(mesh.source_image_urls),
            mesh.texture,
            recoverable_mesh_response(mesh.provider_response_metadata),
        )
    start = time.monotonic()
    try:
        if source_url is None:
            raise ValueError("This mesh job has no frozen input image")
        reused_provider_result = saved_response is not None
        if saved_response is None:
            prepared = provider.prepare(
                source_url=source_url,
                image_urls=image_urls,
                textured=texture == "standard",
            )
            with session_factory.begin() as db:
                mesh = db.get(VersionMesh, version_id)
                mesh.request_payload = prepared.payload
                mesh.model = prepared.endpoint
            _log_fal_request(
                operation="submit",
                prepared=prepared,
                provider=provider,
                frozen_image_urls=image_urls,
            )
            request_id = provider.transport.submit(
                endpoint=prepared.endpoint, payload=prepared.payload
            )
            with session_factory.begin() as db:
                mesh = db.get(VersionMesh, version_id)
                mesh.provider_request_id = request_id
                mesh.status = "provider_pending"
            _log_fal_request(
                operation="result",
                prepared=prepared,
                provider=provider,
                frozen_image_urls=image_urls,
            )
            response = provider.transport.result(
                endpoint=prepared.endpoint, request_id=request_id
            )
        else:
            response = saved_response
        with session_factory.begin() as db:
            mesh = db.get(VersionMesh, version_id)
            mesh.status = "ingesting"
            mesh.provider_response_metadata = {
                "provider_response": snapshot_mesh_response(response),
                "reused_provider_result": reused_provider_result,
            }
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
                "task_id": response.get("task_id"),
                "artifact_sha256": stored.model.sha256,
                "artifact_storage_key": stored.model.storage_key,
                "byte_size": stored.model.byte_size,
                "provider_response": snapshot_mesh_response(response),
                "reused_provider_result": reused_provider_result,
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


def _log_fal_request(
    *,
    operation: str,
    prepared: PreparedMeshRequest,
    provider: MeshProvider,
    frozen_image_urls: list[str],
) -> None:
    # Keep this immediately before each model request. The payload URLs are the
    # exact uploaded URLs sent to fal, while frozen_image_urls verifies the
    # version-level four-view contract before any request can be submitted.
    endpoint = prepared.endpoint
    payload = prepared.payload
    request_image_urls = payload.get("image_urls")
    if isinstance(request_image_urls, list):
        image_count = len(request_image_urls)
        logged_urls = request_image_urls
    else:
        image_count = 1
        logged_urls = [payload.get("image_url")]
    if len(frozen_image_urls) > 1 or endpoint == TRELLIS_ENDPOINT:
        if not provider.multi_image_enabled or endpoint != TRELLIS_ENDPOINT:
            raise ValueError("Multi-angle jobs require the TRELLIS-2 /multi route")
        if (
            len(frozen_image_urls) != 4
            or not isinstance(request_image_urls, list)
            or len(request_image_urls) != 4
            or any(not isinstance(url, str) or not url for url in request_image_urls)
            or len(set(request_image_urls)) != 4
            or "image_url" in payload
        ):
            raise ValueError(
                "A 4-view mesh job must send exactly four distinct URLs via "
                "image_urls; single-image fallback is forbidden"
            )
    resolution = payload.get("resolution")
    texture_size = payload.get("texture_size")
    sampling_steps = {
        "ss": payload.get("ss_sampling_steps"),
        "shape_slat": payload.get("shape_slat_sampling_steps"),
        "tex_slat": payload.get("tex_slat_sampling_steps"),
    }
    logger.info(
        "fal 3D request operation=%s model_id=%s preset=%s multi_image_enabled=%s "
        "image_count=%s image_urls=%s resolution=%s texture_size=%s "
        "sampling_steps=%s",
        operation,
        endpoint,
        provider.preset.name,
        provider.multi_image_enabled,
        image_count,
        logged_urls,
        resolution,
        texture_size,
        sampling_steps,
    )
