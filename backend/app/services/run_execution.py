import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.runs import FrozenRunRequest
from app.models.graph import GraphNode, RunJob, Version
from app.models.project import Project
from app.providers.base import ImageProvider, ProviderJob
from app.services.frozen_request_codec import decode_frozen_request
from app.storage.artifacts import ArtifactIngestor, StoredArtifact


class RunExecutionError(RuntimeError):
    pass


def execute_run_job(
    *,
    job_id: uuid.UUID,
    session_factory: sessionmaker[Session],
    provider: ImageProvider,
    ingestor: ArtifactIngestor,
) -> uuid.UUID:
    run_started = time.monotonic()
    request = _claim_job(job_id=job_id, session_factory=session_factory)
    provider_started: float | None = None
    provider_elapsed: float | None = None
    try:
        provider_started = time.monotonic()
        provider_job = provider.execute(request)
        _record_provider_job(
            job_id=job_id,
            provider_job=provider_job,
            session_factory=session_factory,
        )
        result = provider.result(provider_job)
        provider_elapsed = time.monotonic() - provider_started
        _record_provider_result(
            job_id=job_id,
            metadata=result.response_metadata,
            provider_elapsed_seconds=provider_elapsed,
            session_factory=session_factory,
        )
        if request.mask is not None:
            artifact = ingestor.ingest_masked(result, request)
        else:
            artifact = ingestor.ingest(result)
        return _commit_version(
            job_id=job_id,
            request=request,
            provider_job=provider_job,
            artifact=artifact,
            response_metadata=result.response_metadata,
            total_elapsed_seconds=time.monotonic() - run_started,
            session_factory=session_factory,
        )
    except Exception as error:
        if provider_started is not None and provider_elapsed is None:
            provider_elapsed = time.monotonic() - provider_started
        _record_failure(
            job_id=job_id,
            error=error,
            provider_elapsed_seconds=provider_elapsed,
            total_elapsed_seconds=time.monotonic() - run_started,
            session_factory=session_factory,
        )
        raise


def _claim_job(
    *, job_id: uuid.UUID, session_factory: sessionmaker[Session]
) -> FrozenRunRequest:
    with session_factory.begin() as db:
        job = db.scalar(select(RunJob).where(RunJob.id == job_id).with_for_update())
        if job is None:
            raise RunExecutionError("Run job not found")
        if job.status == "complete":
            version_id = db.scalar(
                select(Version.id).where(Version.run_job_id == job.id)
            )
            raise RunExecutionError(f"Run already completed as {version_id}")
        if job.status != "queued":
            raise RunExecutionError(
                "Run is not safe to submit again; inspect its recorded provider state"
            )
        job.status = "dispatching"
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        return decode_frozen_request(job.frozen_request)


def _record_provider_job(
    *,
    job_id: uuid.UUID,
    provider_job: ProviderJob,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as db:
        job = _lock_job(db, job_id)
        job.provider = provider_job.provider
        job.model = provider_job.model
        job.endpoint = provider_job.endpoint
        job.provider_request_id = provider_job.request_id
        job.provider_request_payload = provider_job.request_payload
        job.status = "provider_pending"


def _record_provider_result(
    *,
    job_id: uuid.UUID,
    metadata: dict[str, object],
    provider_elapsed_seconds: float,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as db:
        job = _lock_job(db, job_id)
        job.provider_response_metadata = metadata
        job.provider_elapsed_seconds = provider_elapsed_seconds
        job.status = "ingesting"


def _commit_version(
    *,
    job_id: uuid.UUID,
    request: FrozenRunRequest,
    provider_job: ProviderJob,
    artifact: StoredArtifact,
    response_metadata: dict[str, object],
    total_elapsed_seconds: float,
    session_factory: sessionmaker[Session],
) -> uuid.UUID:
    with session_factory.begin() as db:
        project_id = db.scalar(select(RunJob.project_id).where(RunJob.id == job_id))
        project = db.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        job = _lock_job(db, job_id)
        existing = db.scalar(select(Version).where(Version.run_job_id == job.id))
        if existing is not None:
            return existing.id
        node = db.scalar(
            select(GraphNode).where(GraphNode.id == job.node_id).with_for_update()
        )
        if node is None:
            raise RunExecutionError("Run target no longer exists")

        if db.scalar(select(Version.id).where(Version.node_id == node.id).limit(1)):
            raise RunExecutionError(
                "This node already has an image. Create a new node."
            )

        version = Version(
            id=uuid.uuid4(),
            node_id=job.node_id,
            run_job_id=job.id,
            artifact_url=artifact.artifact_url,
            artifact_storage_key=artifact.storage_key,
            artifact_sha256=artifact.sha256,
            artifact_content_type=artifact.content_type,
            op=request.op.value,
            provider=provider_job.provider,
            model=provider_job.model,
            endpoint=provider_job.endpoint,
            params={
                **provider_job.request_payload,
                "whiteBackground": request.settings.white_background,
            },
            provider_response_metadata=response_metadata,
            seed=request.seed,
            input_snapshot={
                "subject_version_id": request.input_snapshot.subject_version_id,
                "connect_version_ids": list(request.input_snapshot.connect_version_ids),
                "mask_hash": request.input_snapshot.mask_hash,
            },
            prompt_at_runtime=request.prompt_at_runtime,
            edit_depth=request.edit_depth,
        )
        db.add(version)
        db.flush()
        node.active_version_id = version.id
        if project is not None:
            project.thumbnail_url = artifact.artifact_url
            project.updated_at = datetime.now(UTC)
        job.status = "complete"
        job.completed_at = datetime.now(UTC)
        job.total_elapsed_seconds = total_elapsed_seconds
        job.error = None
        return version.id


def _record_failure(
    *,
    job_id: uuid.UUID,
    error: Exception,
    provider_elapsed_seconds: float | None,
    total_elapsed_seconds: float,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as db:
        job = db.scalar(select(RunJob).where(RunJob.id == job_id).with_for_update())
        if job is None or job.status == "complete":
            return
        job.status = "failed"
        job.error = f"{type(error).__name__}: {error}"[:8000]
        job.completed_at = datetime.now(UTC)
        if job.provider_elapsed_seconds is None:
            job.provider_elapsed_seconds = provider_elapsed_seconds
        job.total_elapsed_seconds = total_elapsed_seconds


def _lock_job(db: Session, job_id: uuid.UUID) -> RunJob:
    job = db.scalar(select(RunJob).where(RunJob.id == job_id).with_for_update())
    if job is None:
        raise RunExecutionError("Run job not found")
    return job
