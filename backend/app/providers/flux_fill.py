from io import BytesIO

from PIL import Image

from app.domain.runs import FrozenRunRequest, Op
from app.providers.base import (
    ArtifactReader,
    PreparedProviderRequest,
    ProviderContractError,
    ProviderJob,
    ProviderResult,
)
from app.providers.fal_transport import FalTransport
from app.services.masks import mask_png, validate_mask


class FluxFillProvider:
    id = "fal"
    model = "flux-1-fill-pro"
    endpoint = "fal-ai/flux-pro/v1/fill"

    def __init__(self, *, transport: FalTransport, artifact_reader: ArtifactReader):
        self._transport = transport
        self._reader = artifact_reader

    def prepare(self, request: FrozenRunRequest) -> PreparedProviderRequest:
        if (
            request.op != Op.EDIT_INPAINT
            or request.subject is None
            or request.mask is None
        ):
            raise ProviderContractError("FLUX Fill requires a subject and partial mask")
        if request.connects:
            raise ProviderContractError("FLUX Fill cannot accept connect images")
        if validate_mask(request.mask):
            raise ProviderContractError(
                "A full-image mask must resolve to an unmasked edit"
            )
        subject = self._reader.read(request.subject.artifact_url)
        if Image.open(BytesIO(subject.content)).size != (
            request.mask.width,
            request.mask.height,
        ):
            raise ProviderContractError("Mask dimensions do not match the subject")
        payload = {
            "prompt": request.prompt_at_runtime,
            "image_url": self._transport.upload(
                content=subject.content, filename=subject.filename
            ),
            "mask_url": self._transport.upload(
                content=mask_png(request.mask), filename="mask.png"
            ),
            "seed": request.seed,
            "num_images": 1,
            "output_format": "png",
            "enhance_prompt": False,
        }
        return PreparedProviderRequest(self.id, self.model, self.endpoint, payload)

    def execute(self, request: FrozenRunRequest) -> ProviderJob:
        prepared = self.prepare(request)
        return ProviderJob(
            self.id,
            self.model,
            self.endpoint,
            self._transport.submit(
                endpoint=self.endpoint, payload=prepared.request_payload
            ),
            prepared.request_payload,
        )

    def result(self, job: ProviderJob) -> ProviderResult:
        response = self._transport.result(
            endpoint=job.endpoint, request_id=job.request_id
        )
        images = response.get("images")
        if (
            not isinstance(images, list)
            or not images
            or not isinstance(images[0], dict)
        ):
            raise ProviderContractError("FLUX Fill returned no image")
        output = images[0]
        if not isinstance(output.get("url"), str):
            raise ProviderContractError("FLUX Fill returned no output URL")
        return ProviderResult(job, output["url"], "image/png", None, None, response)
