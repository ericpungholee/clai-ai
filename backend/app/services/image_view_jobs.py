import uuid
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.graph import Version, VersionImageView
from app.providers.base import ProviderJob, ProviderResult
from app.storage.artifacts import ArtifactIngestor


class AngleViewProvider(Protocol):
    def execute_angle_view(
        self,
        *,
        source_url: str,
        aspect_ratio: str,
        resolution: str,
        seed: int,
        white_background: bool,
        angle: str,
        design_prompt: str,
    ) -> ProviderJob: ...

    def result(self, job: ProviderJob) -> ProviderResult: ...


def execute_image_view_job(
    *,
    version_id: uuid.UUID,
    angle: str,
    session_factory: sessionmaker[Session],
    provider: AngleViewProvider,
    ingestor: ArtifactIngestor,
) -> None:
    with session_factory.begin() as db:
        version = db.get(Version, version_id)
        if version is None:
            return
        view = db.scalar(
            select(VersionImageView)
            .where(
                VersionImageView.version_id == version_id,
                VersionImageView.angle == angle,
            )
            .with_for_update()
        )
        # Rows are created with the primary version. Claim once, including on
        # duplicate delivery; a failed angle never blocks its siblings.
        if view is None or view.status != "queued":
            return
        view.status = "dispatching"
        view.started_at = datetime.now(UTC)
        source_url = view.source_artifact_url
        aspect_ratio, resolution, white_background = _view_settings(version.params)
        seed = version.seed
        design_prompt = version.prompt_at_runtime
    try:
        provider_job = provider.execute_angle_view(
            source_url=source_url,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            seed=seed,
            white_background=white_background,
            angle=angle,
            design_prompt=design_prompt,
        )
        with session_factory.begin() as db:
            view = db.get(VersionImageView, (version_id, angle))
            if view is None:
                return
            view.provider = provider_job.provider
            view.model = provider_job.model
            view.endpoint = provider_job.endpoint
            view.provider_request_id = provider_job.request_id
            view.request_payload = provider_job.request_payload
            view.status = "provider_pending"
        result = provider.result(provider_job)
        with session_factory.begin() as db:
            view = db.get(VersionImageView, (version_id, angle))
            if view is None:
                return
            view.status = "ingesting"
        artifact = ingestor.ingest(result)
        with session_factory.begin() as db:
            view = db.get(VersionImageView, (version_id, angle))
            if view is None:
                return
            view.artifact_url = artifact.artifact_url
            view.artifact_storage_key = artifact.storage_key
            view.artifact_sha256 = artifact.sha256
            view.artifact_content_type = artifact.content_type
            view.status = "complete"
            view.error = None
    except Exception as error:
        with session_factory.begin() as db:
            view = db.get(VersionImageView, (version_id, angle))
            if view is None or view.status == "complete":
                return
            view.status = "failed"
            view.error = f"{type(error).__name__}: {error}"[:8000]
        raise


def _view_settings(params: dict[str, object]) -> tuple[str, str, bool]:
    aspect_ratio = params.get("aspect_ratio")
    if not isinstance(aspect_ratio, str) or not aspect_ratio.strip():
        aspect_ratio = "1:1"
    resolution = params.get("resolution")
    if resolution not in {"1K", "2K", "4K"}:
        resolution = "1K"
    white_background = params.get("whiteBackground")
    if not isinstance(white_background, bool):
        white_background = True
    return aspect_ratio, resolution, white_background
