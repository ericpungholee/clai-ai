from app.domain.runs import FrozenRunRequest, Op, VersionSnapshot
from app.providers.base import (
    ArtifactReader,
    PreparedProviderRequest,
    ProviderContractError,
    ProviderJob,
    ProviderResult,
)
from app.providers.fal_transport import FalTransport


class NanoBananaProProvider:
    id = "fal"
    model = "gemini-3-pro-image"
    generate_endpoint = "fal-ai/nano-banana-pro"
    edit_endpoint = "fal-ai/nano-banana-pro/edit"

    _generate_ops = frozenset({Op.GENERATE})
    _edit_ops = frozenset(
        {
            Op.GENERATE_REF,
            Op.EDIT_INSTRUCT,
            Op.EDIT_REF_GUIDED,
        }
    )
    _aspect_ratios = frozenset(
        {
            "auto",
            "21:9",
            "16:9",
            "3:2",
            "4:3",
            "5:4",
            "1:1",
            "4:5",
            "3:4",
            "2:3",
            "9:16",
        }
    )

    def __init__(
        self,
        *,
        transport: FalTransport,
        artifact_reader: ArtifactReader,
    ) -> None:
        self._transport = transport
        self._artifact_reader = artifact_reader

    def execute(self, request: FrozenRunRequest) -> ProviderJob:
        return self.submit(self.prepare(request))

    def prepare(self, request: FrozenRunRequest) -> PreparedProviderRequest:
        endpoint = self._endpoint_for(request)
        payload = self._build_payload(request)
        return PreparedProviderRequest(
            provider=self.id,
            model=self.model,
            endpoint=endpoint,
            request_payload=payload,
        )

    def submit(self, request: PreparedProviderRequest) -> ProviderJob:
        if request.provider != self.id or request.model != self.model:
            raise ProviderContractError(
                "The prepared request does not belong to this provider"
            )
        request_id = self._transport.submit(
            endpoint=request.endpoint,
            payload=request.request_payload,
        )
        return ProviderJob(
            provider=request.provider,
            model=request.model,
            endpoint=request.endpoint,
            request_id=request_id,
            request_payload=request.request_payload,
        )

    def result(self, job: ProviderJob) -> ProviderResult:
        if job.provider != self.id or job.endpoint not in {
            self.generate_endpoint,
            self.edit_endpoint,
        }:
            raise ProviderContractError("The job does not belong to this provider")

        response = self._transport.result(
            endpoint=job.endpoint,
            request_id=job.request_id,
        )
        images = response.get("images")
        if not isinstance(images, list) or not images:
            raise ProviderContractError("fal response is missing its output image")
        image = images[0]
        if not isinstance(image, dict):
            raise ProviderContractError("fal returned an invalid output image")

        output_url = image.get("url")
        if not isinstance(output_url, str) or not output_url:
            raise ProviderContractError("fal output image is missing its URL")

        content_type = image.get("content_type", "image/png")
        if not isinstance(content_type, str):
            raise ProviderContractError("fal output content type is invalid")

        width = image.get("width")
        height = image.get("height")
        return ProviderResult(
            job=job,
            output_url=output_url,
            content_type=content_type,
            width=width if isinstance(width, int) else None,
            height=height if isinstance(height, int) else None,
            response_metadata=response,
        )

    def _endpoint_for(self, request: FrozenRunRequest) -> str:
        if request.op in self._generate_ops:
            return self.generate_endpoint
        if request.op in self._edit_ops:
            return self.edit_endpoint
        raise ProviderContractError(
            f"Nano Banana Pro cannot execute operation {request.op.value}"
        )

    def _build_payload(self, request: FrozenRunRequest) -> dict[str, object]:
        if request.mask is not None:
            raise ProviderContractError("Nano Banana Pro cannot accept a mask")
        if request.settings.aspect_ratio not in self._aspect_ratios:
            raise ProviderContractError("Unsupported Nano Banana Pro aspect ratio")

        width, height = request.settings.width, request.settings.height
        if width > 4096 or height > 4096:
            raise ProviderContractError(
                "Requested resolution exceeds provider capability"
            )

        payload: dict[str, object] = {
            "prompt": request.prompt_at_runtime,
            "num_images": 1,
            "seed": request.seed,
            "aspect_ratio": request.settings.aspect_ratio,
            "output_format": "png",
            "resolution": _resolution_label(width=width, height=height),
            "limit_generations": True,
            "enable_web_search": False,
        }

        input_versions = _input_versions(request)
        if len(input_versions) > 3:
            raise ProviderContractError("Too many input images for Nano Banana Pro")
        if request.op in self._generate_ops and input_versions:
            raise ProviderContractError("Generate cannot include input images")
        if request.op in self._edit_ops and not input_versions:
            raise ProviderContractError(
                "Edit endpoint requires at least one input image"
            )

        if input_versions:
            payload["image_urls"] = [
                self._upload(version) for version in input_versions
            ]
        return payload

    def _upload(self, version: VersionSnapshot) -> str:
        artifact = self._artifact_reader.read(version.artifact_url)
        return self._transport.upload(
            content=artifact.content,
            filename=artifact.filename,
        )


def _input_versions(request: FrozenRunRequest) -> tuple[VersionSnapshot, ...]:
    if request.subject is None:
        return request.connects
    return (request.subject, *request.connects)


def _resolution_label(*, width: int, height: int) -> str:
    largest_dimension = max(width, height)
    if largest_dimension <= 1024:
        return "1K"
    if largest_dimension <= 2048:
        return "2K"
    return "4K"
