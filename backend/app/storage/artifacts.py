import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.providers.base import ArtifactBytes, ProviderResult


@dataclass(frozen=True)
class StoredArtifact:
    storage_key: str
    artifact_url: str
    content_type: str
    byte_size: int
    sha256: str


class ArtifactStore(Protocol):
    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact: ...


class S3Client(Protocol):
    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        CacheControl: str,
        Metadata: dict[str, str],
    ) -> object: ...


class ArtifactStorageError(ValueError):
    pass


class HttpArtifactReader:
    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        timeout_seconds: float = 30.0,
        max_bytes: int = 32 * 1024 * 1024,
        client: httpx.Client | None = None,
    ) -> None:
        if not allowed_hosts:
            raise ValueError("At least one artifact host must be allowed")
        self._allowed_hosts = allowed_hosts
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._client = client or httpx.Client()

    def read(self, artifact_url: str) -> ArtifactBytes:
        parsed = urlparse(artifact_url)
        if parsed.scheme != "https" or parsed.hostname not in self._allowed_hosts:
            raise ArtifactStorageError("Artifact URL is not on an allowed HTTPS host")

        with self._client.stream(
            "GET",
            artifact_url,
            timeout=self._timeout_seconds,
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            byte_size = 0
            for chunk in response.iter_bytes():
                byte_size += len(chunk)
                if byte_size > self._max_bytes:
                    raise ArtifactStorageError(
                        "Artifact exceeds the download size limit"
                    )
                chunks.append(chunk)

        content_type = response.headers.get("content-type", "application/octet-stream")
        return ArtifactBytes(
            content=b"".join(chunks),
            content_type=content_type.split(";", maxsplit=1)[0],
            filename=Path(parsed.path).name or "artifact.bin",
        )


class FileArtifactStore:
    def __init__(self, *, root: Path, public_base_url: str) -> None:
        self._root = root.resolve()
        self._public_base_url = public_base_url.rstrip("/")
        self._root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact:
        storage_key = _content_addressed_key(key=key, content=content)
        destination = _safe_destination(self._root, storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            if destination.read_bytes() != content:
                raise ArtifactStorageError(
                    "Refusing to overwrite an immutable artifact"
                )
        else:
            descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent)
            try:
                with os.fdopen(descriptor, "wb") as temporary:
                    temporary.write(content)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, destination)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)

        digest = sha256(content).hexdigest()
        return StoredArtifact(
            storage_key=storage_key,
            artifact_url=f"{self._public_base_url}/{storage_key}",
            content_type=content_type,
            byte_size=len(content),
            sha256=digest,
        )


class S3ArtifactStore:
    def __init__(
        self,
        *,
        client: S3Client,
        bucket: str,
        public_base_url: str,
        prefix: str = "artifacts",
    ) -> None:
        if not bucket:
            raise ValueError("An artifact bucket is required")
        self._client = client
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._prefix = prefix.strip("/")

    def put(
        self,
        *,
        key: str,
        content: bytes,
        content_type: str,
    ) -> StoredArtifact:
        content_key = _content_addressed_key(key=key, content=content)
        storage_key = f"{self._prefix}/{content_key}" if self._prefix else content_key
        digest = sha256(content).hexdigest()
        self._client.put_object(
            Bucket=self._bucket,
            Key=storage_key,
            Body=content,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"sha256": digest},
        )
        return StoredArtifact(
            storage_key=storage_key,
            artifact_url=f"{self._public_base_url}/{storage_key}",
            content_type=content_type,
            byte_size=len(content),
            sha256=digest,
        )


class ArtifactIngestor:
    def __init__(self, *, reader: HttpArtifactReader, store: ArtifactStore) -> None:
        self._reader = reader
        self._store = store

    def ingest(self, result: ProviderResult) -> StoredArtifact:
        artifact = self._reader.read(result.output_url)
        extension = _extension_for(artifact.content_type)
        return self._store.put(
            key=f"runs/{result.job.request_id}/output{extension}",
            content=artifact.content,
            content_type=artifact.content_type,
        )


def _content_addressed_key(*, key: str, content: bytes) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ArtifactStorageError("Artifact storage key is invalid")
    digest = sha256(content).hexdigest()
    return str(path.parent / digest / path.name)


def _safe_destination(root: Path, storage_key: str) -> Path:
    destination = (root / storage_key).resolve()
    if not destination.is_relative_to(root):
        raise ArtifactStorageError("Artifact storage key escapes its root")
    return destination


def _extension_for(content_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(content_type, ".bin")
