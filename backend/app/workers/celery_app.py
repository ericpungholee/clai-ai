import uuid

from celery import Celery

from app.core.config import settings
from app.core.database import SessionLocal
from app.providers.factory import create_nano_banana_provider
from app.services.drift import create_change_magnitude_scorer
from app.services.run_execution import execute_run_job
from app.storage.factory import create_artifact_reader, create_provider_output_ingestor

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
    artifact_reader = create_artifact_reader(settings)
    version_id = execute_run_job(
        job_id=uuid.UUID(job_id),
        session_factory=SessionLocal,
        provider=create_nano_banana_provider(
            settings=settings,
            artifact_reader=artifact_reader,
        ),
        ingestor=create_provider_output_ingestor(settings),
        scorer=create_change_magnitude_scorer(
            settings=settings,
            artifact_reader=artifact_reader,
        ),
    )
    return str(version_id)
