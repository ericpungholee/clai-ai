import uuid
from datetime import UTC, datetime

from celery import Celery
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.graph import RunJob, VersionMesh
from app.providers.factory import FalImageProvider
from app.providers.fal_transport import FalSdkTransport
from app.providers.tripo import TripoProvider
from app.services.mesh_jobs import execute_mesh_job
from app.services.run_execution import execute_run_job
from app.storage.artifacts import HttpArtifactReader
from app.storage.factory import (
    create_artifact_reader,
    create_artifact_store,
    create_provider_output_ingestor,
)

celery_app = Celery(
    "clai",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="clai.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="clai.run_job")
def run_job(job_id: str) -> str:
    try:
        artifact_reader = create_artifact_reader(settings)
        provider = FalImageProvider(settings=settings, artifact_reader=artifact_reader)
        ingestor = create_provider_output_ingestor(settings)
    except Exception as error:
        with SessionLocal.begin() as db:
            job = db.scalar(
                select(RunJob).where(RunJob.id == uuid.UUID(job_id)).with_for_update()
            )
            if job is not None and job.status == "queued":
                job.status = "failed"
                job.error = f"Worker setup failed before generation: {error}"[:8000]
                job.completed_at = datetime.now(UTC)
        raise
    version_id = execute_run_job(
        job_id=uuid.UUID(job_id),
        session_factory=SessionLocal,
        provider=provider,
        ingestor=ingestor,
    )
    return str(version_id)


@celery_app.task(name="clai.mesh_job")
def mesh_job(version_id: str, attempt_id: str) -> None:
    try:
        if settings.fal_api_key is None:
            raise ValueError("FAL_KEY is required")
        provider = TripoProvider(
            FalSdkTransport(settings.fal_api_key), create_artifact_reader(settings)
        )
        output_reader = HttpArtifactReader(
            allowed_hosts=frozenset(settings.fal_output_host_list),
            max_bytes=128 * 1024 * 1024,
        )
        store = create_artifact_store(settings)
    except Exception as error:
        with SessionLocal.begin() as db:
            mesh = db.scalar(
                select(VersionMesh)
                .where(VersionMesh.version_id == uuid.UUID(version_id))
                .with_for_update()
            )
            if (
                mesh is not None
                and mesh.status == "queued"
                and mesh.attempt_id == uuid.UUID(attempt_id)
            ):
                mesh.status = "failed"
                mesh.error = (
                    f"The 3D worker could not start. Your image is unchanged. {error}"[
                        :4000
                    ]
                )
        raise
    execute_mesh_job(
        version_id=uuid.UUID(version_id),
        attempt_id=uuid.UUID(attempt_id),
        session_factory=SessionLocal,
        provider=provider,
        output_reader=output_reader,
        store=store,
    )
