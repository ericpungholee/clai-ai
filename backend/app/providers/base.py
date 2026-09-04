from dataclasses import dataclass
from typing import Protocol

from app.domain.runs import FrozenRunRequest


@dataclass(frozen=True)
class ProviderCapabilities:
    mask: bool
    references: int
    seed: bool
    max_resolution: tuple[int, int]


@dataclass(frozen=True)
class ArtifactBytes:
    content: bytes
    content_type: str
    filename: str


class ArtifactReader(Protocol):
    def read(self, artifact_url: str) -> ArtifactBytes: ...


@dataclass(frozen=True)
class ProviderJob:
    provider: str
    model: str
    endpoint: str
    request_id: str
    request_payload: dict[str, object]


@dataclass(frozen=True)
class PreparedProviderRequest:
    provider: str
    model: str
    endpoint: str
    request_payload: dict[str, object]


@dataclass(frozen=True)
class ProviderResult:
    job: ProviderJob
    output_url: str
    content_type: str
    width: int | None
    height: int | None
    response_metadata: dict[str, object]


class ProviderContractError(ValueError):
    pass


class ImageProvider(Protocol):
    id: str
    capabilities: ProviderCapabilities

    def execute(self, request: FrozenRunRequest) -> ProviderJob: ...

    def result(self, job: ProviderJob) -> ProviderResult: ...
