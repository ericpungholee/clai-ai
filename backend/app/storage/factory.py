from typing import cast
from urllib.parse import urlparse

import boto3

from app.core.config import Settings
from app.providers.base import ArtifactReader
from app.storage.artifacts import (
    ArtifactIngestor,
    ArtifactStore,
    FileArtifactReader,
    FileArtifactStore,
    HttpArtifactReader,
    S3ArtifactStore,
    S3Client,
)


def create_artifact_store(settings: Settings) -> ArtifactStore:
    if settings.artifact_storage_backend == "filesystem":
        return FileArtifactStore(
            root=settings.artifact_storage_path,
            public_base_url=settings.artifact_public_base_url,
        )

    bucket = settings.artifact_s3_bucket
    access_key = settings.artifact_s3_access_key_id
    secret_key = settings.artifact_s3_secret_access_key
    if bucket is None or access_key is None or secret_key is None:
        raise ValueError(
            "S3 artifact storage requires bucket, access key, and secret key"
        )
    client = boto3.client(
        "s3",
        endpoint_url=settings.artifact_s3_endpoint_url,
        region_name=settings.artifact_s3_region,
        aws_access_key_id=access_key.get_secret_value(),
        aws_secret_access_key=secret_key.get_secret_value(),
    )
    return S3ArtifactStore(
        client=cast(S3Client, client),
        bucket=bucket,
        public_base_url=settings.artifact_public_base_url,
    )


def create_artifact_reader(settings: Settings) -> ArtifactReader:
    if settings.artifact_storage_backend == "filesystem":
        return FileArtifactReader(
            root=settings.artifact_storage_path,
            public_base_url=settings.artifact_public_base_url,
        )
    parsed = urlparse(settings.artifact_public_base_url)
    if parsed.scheme != "https" or parsed.hostname is None:
        raise ValueError("Remote artifact public URL must use HTTPS")
    return HttpArtifactReader(allowed_hosts=frozenset({parsed.hostname}))


def create_provider_output_ingestor(settings: Settings) -> ArtifactIngestor:
    return ArtifactIngestor(
        reader=HttpArtifactReader(
            allowed_hosts=frozenset(settings.fal_output_host_list)
        ),
        store=create_artifact_store(settings),
    )
