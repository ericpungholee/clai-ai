import uuid
from typing import Protocol


class RunEnqueuer(Protocol):
    def enqueue(self, job_id: uuid.UUID) -> None: ...


class CeleryRunEnqueuer:
    def enqueue(self, job_id: uuid.UUID) -> None:
        from app.workers.celery_app import run_job

        run_job.delay(str(job_id))


def get_run_enqueuer() -> RunEnqueuer:
    return CeleryRunEnqueuer()
