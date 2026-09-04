from typing import cast

import boto3

from app.core.config import Settings
from app.storage.artifacts import (
    ArtifactStore,
    FileArtifactStore,
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
