import tempfile
import time
from pathlib import Path
from typing import Protocol, cast

import httpx
from fal_client import Completed, FalClientHTTPError


class FalAccountError(RuntimeError):
    pass


def _check_account_error(response: httpx.Response) -> None:
    if response.status_code != 403:
        return
    try:
        body = response.json()
    except ValueError:
        body = None
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, str) and "exhausted balance" in detail.lower():
        # Translate the known billing response without exposing arbitrary provider
        # response bodies, credentials, or storage authorization tokens in the UI.
        raise FalAccountError(
            "fal rejected the request with an 'Exhausted balance' account error. "
            "Check https://fal.ai/dashboard/billing for the account associated "
            "with FAL_KEY. If that account has credits, contact support@fal.ai "
            "to check its billing status and clear any account lock, then retry."
        )
    raise FalAccountError(
        "fal denied access (403). Check the account, permissions and billing for "
        "the configured FAL_KEY. If the key changed, ensure the worker uses the "
        "updated key. No replacement generation was submitted."
    )


class FalTransport(Protocol):
    def upload(self, *, content: bytes, filename: str) -> str: ...

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str: ...

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]: ...


class FalHandle(Protocol):
    response_url: str

    def status(self, *, with_logs: bool = False) -> object: ...


class FalClient(Protocol):
    def upload_file(self, path: str) -> str: ...

    def get_handle(self, application: str, request_id: str) -> FalHandle: ...


class FalSdkTransport:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 120.0,
        queue_origin: str = "https://queue.fal.run",
        queue_poll_interval_seconds: float = 1.0,
        queue_timeout_seconds: float = 900.0,
        client: FalClient | None = None,
        queue_client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("A fal API key is required")
        if queue_poll_interval_seconds <= 0:
            raise ValueError("The fal queue polling interval must be positive")
        if queue_timeout_seconds <= 0:
            raise ValueError("The fal queue timeout must be positive")

        if client is None:
            import fal_client

            client = fal_client.SyncClient(
                key=api_key,
                default_timeout=timeout_seconds,
            )
        self._client = client
        self._queue_poll_interval_seconds = queue_poll_interval_seconds
        self._queue_timeout_seconds = queue_timeout_seconds
        self._queue_origin = queue_origin.rstrip("/")
        self._queue_client = queue_client or httpx.Client(
            headers={"Authorization": f"Key {api_key}"}, timeout=timeout_seconds
        )

    def upload(self, *, content: bytes, filename: str) -> str:
        suffix = Path(filename).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix) as upload:
            upload.write(content)
            upload.flush()
            try:
                return self._client.upload_file(upload.name)
            except (httpx.HTTPStatusError, FalClientHTTPError) as error:
                _check_account_error(error.response)
                raise

    def submit(self, *, endpoint: str, payload: dict[str, object]) -> str:
        response = self._queue_client.post(
            f"{self._queue_origin}/{endpoint}",
            json=payload,
        )
        _check_account_error(response)
        response.raise_for_status()
        body = response.json()
        request_id = body.get("request_id") if isinstance(body, dict) else None
        if not isinstance(request_id, str) or not request_id:
            raise TypeError("fal submission response is missing its request ID")
        return request_id

    def result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        # SDK get() polls forever; a network timeout does not bound queue time.
        try:
            return self._result(endpoint=endpoint, request_id=request_id)
        except (httpx.HTTPStatusError, FalClientHTTPError) as error:
            _check_account_error(error.response)
            raise

    def _result(self, *, endpoint: str, request_id: str) -> dict[str, object]:
        handle = self._client.get_handle(endpoint, request_id)
        deadline = time.monotonic() + self._queue_timeout_seconds
        while not isinstance(handle.status(with_logs=False), Completed):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "fal generation exceeded its queue time limit. "
                    f"Request {request_id} is recorded; no replacement was submitted."
                )
            time.sleep(min(self._queue_poll_interval_seconds, remaining))
        result = self._queue_client.get(handle.response_url)
        _check_account_error(result)
        result.raise_for_status()
        response = result.json()
        if not isinstance(response, dict):
            raise TypeError("fal returned a non-object response")
        return cast(dict[str, object], response)
