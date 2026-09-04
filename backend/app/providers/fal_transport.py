import tempfile
from pathlib import Path
from typing import Protocol, cast

import httpx


class FalTransport(Protocol):
    def upload(self, *, content: bytes, filename: str) -> str: ...

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str: ...

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]: ...


class FalClient(Protocol):
    def upload_file(self, path: str) -> str: ...

    def result(self, application: str, request_id: str) -> object: ...


class FalSdkTransport:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 120.0,
        queue_origin: str = "https://queue.fal.run",
        client: FalClient | None = None,
        queue_client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("A fal API key is required")

        if client is None:
            import fal_client

            client = fal_client.SyncClient(
                key=api_key,
                default_timeout=timeout_seconds,
            )
        self._client = client
        self._queue_origin = queue_origin.rstrip("/")
        self._queue_client = queue_client or httpx.Client(
            headers={"Authorization": f"Key {api_key}"}, timeout=timeout_seconds
        )

    def upload(self, *, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as upload:
            upload.write(content)
            upload.flush()
            return self._client.upload_file(upload.name)

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str:
        response = self._queue_client.post(
            f"{self._queue_origin}/{endpoint}",
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        request_id = body.get("request_id") if isinstance(body, dict) else None
        if not isinstance(request_id, str) or not request_id:
            raise TypeError("fal submission response is missing its request ID")
        return request_id

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        response = self._client.result(endpoint, request_id)
        if not isinstance(response, dict):
            raise TypeError("fal returned a non-object response")
        return cast(dict[str, object], response)
