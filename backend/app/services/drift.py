import shlex
import subprocess
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.domain.runs import FrozenRunRequest
from app.providers.base import ArtifactReader
from app.services.run_execution import (
    ChangeMagnitudeResult,
    ChangeMagnitudeScorer,
    PendingDinoV2Scorer,
)
from app.storage.artifacts import StoredArtifact


class CommandDinoV2Scorer:
    def __init__(
        self,
        *,
        command: tuple[str, ...],
        artifact_reader: ArtifactReader,
        timeout_seconds: float,
    ) -> None:
        if not command:
            raise ValueError("DINOv2 scorer command cannot be empty")
        self._command = command
        self._artifact_reader = artifact_reader
        self._timeout_seconds = timeout_seconds

    def score(
        self, *, request: FrozenRunRequest, artifact: StoredArtifact
    ) -> ChangeMagnitudeResult:
        if request.subject is None:
            return ChangeMagnitudeResult(method="dinov2_cosine", status="pending")
        try:
            subject = self._artifact_reader.read(request.subject.artifact_url)
            output = self._artifact_reader.read(artifact.artifact_url)
            with tempfile.TemporaryDirectory(prefix="clai-drift-") as directory:
                root = Path(directory)
                # Both immutable artifacts are commonly named output.png.
                subject_path = root / f"subject{Path(subject.filename).suffix}"
                output_path = root / f"generated{Path(output.filename).suffix}"
                subject_path.write_bytes(subject.content)
                output_path.write_bytes(output.content)
                completed = subprocess.run(
                    [*self._command, str(subject_path), str(output_path)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds,
                )
            value = float(completed.stdout.strip())
            if not 0 <= value <= 1:
                raise ValueError("DINOv2 scorer returned a value outside [0, 1]")
            return ChangeMagnitudeResult(
                method="dinov2_cosine", status="complete", value=value
            )
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            return ChangeMagnitudeResult(
                method="dinov2_cosine",
                status="failed",
                error=f"{type(error).__name__}: {error}"[:8000],
            )


def create_change_magnitude_scorer(
    *, settings: Settings, artifact_reader: ArtifactReader
) -> ChangeMagnitudeScorer:
    if settings.drift_scorer_command is None:
        return PendingDinoV2Scorer()
    command = tuple(shlex.split(settings.drift_scorer_command))
    return CommandDinoV2Scorer(
        command=command,
        artifact_reader=artifact_reader,
        timeout_seconds=settings.drift_scorer_timeout_seconds,
    )
