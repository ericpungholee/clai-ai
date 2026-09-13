"""Image generation and reference edits through the current fal stack."""

from concurrent.futures import ThreadPoolExecutor
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
from app.services.masks import decode_rle, validate_mask


class GptImageProvider:
    id = "fal"
    model = "gpt-image-2.5-sunburst"
    generate_endpoint = "openai/gpt-image-2.5/sunburst/text-to-image"
    edit_endpoint = "openai/gpt-image-2.5/sunburst/edit"
    _edit_ops = {Op.GENERATE_REF, Op.EDIT_INSTRUCT, Op.EDIT_REF_GUIDED, Op.EDIT_INPAINT}

    def __init__(self, *, transport: FalTransport, artifact_reader: ArtifactReader):
        self._transport = transport
        self._reader = artifact_reader

    def execute(self, request: FrozenRunRequest) -> ProviderJob:
        return self.submit(self.prepare(request))

    def prepare(self, request: FrozenRunRequest) -> PreparedProviderRequest:
        if request.op != Op.GENERATE and request.op not in self._edit_ops:
            raise ProviderContractError(
                f"Unsupported image operation {request.op.value}"
            )
        if request.mask is not None and request.connects:
            raise ProviderContractError("Masked edits cannot accept connect images")
        versions = ((request.subject,) if request.subject else ()) + request.connects
        if len(versions) > 16:
            raise ProviderContractError("Too many input images for GPT Image")
        if (request.op == Op.GENERATE) == bool(versions):
            raise ProviderContractError(
                "Generate needs no inputs; editing requires inputs"
            )
        payload = self._payload(request=request, prompt=request.prompt_at_runtime)
        mask_content = None
        subject_content = None
        if request.mask is not None:
            if request.op != Op.EDIT_INPAINT or request.subject is None:
                raise ProviderContractError(
                    "A mask requires a subject and inpaint operation"
                )
            if validate_mask(request.mask):
                raise ProviderContractError(
                    "A full-image mask must resolve to an unmasked edit"
                )
            subject = self._reader.read(request.subject.artifact_url)
            with Image.open(BytesIO(subject.content)) as image:
                if image.size != (request.mask.width, request.mask.height):
                    raise ProviderContractError(
                        "Mask dimensions do not match the subject"
                    )
                # GPT Image requires matching image/mask formats and transparent edits.
                buffer = BytesIO()
                image.convert("RGBA").save(buffer, "PNG")
                subject_content = buffer.getvalue()
            pixels = decode_rle(
                request.mask.rle, request.mask.width, request.mask.height
            )
            mask = Image.new("RGBA", (request.mask.width, request.mask.height), "white")
            mask.putalpha(Image.fromarray((~pixels).astype("uint8") * 255))
            buffer = BytesIO()
            mask.save(buffer, "PNG")
            mask_content = buffer.getvalue()
        elif request.op == Op.EDIT_INPAINT:
            raise ProviderContractError("Inpaint requires a partial mask")
        if versions:

            def upload_input(item):
                index, version = item
                return (
                    self._transport.upload(
                        content=subject_content, filename="subject.png"
                    )
                    if index == 0 and subject_content is not None
                    else self._upload(version.artifact_url)
                )

            with ThreadPoolExecutor(max_workers=min(4, len(versions))) as pool:
                payload["image_urls"] = list(
                    pool.map(upload_input, enumerate(versions))
                )
        if mask_content is not None:
            payload["mask_url"] = self._transport.upload(
                content=mask_content, filename="mask.png"
            )
        return PreparedProviderRequest(
            self.id,
            f"gpt-image-2.5-{request.settings.image_model}",
            f"openai/gpt-image-2.5/{request.settings.image_model}/"
            + ("text-to-image" if request.op == Op.GENERATE else "edit"),
            payload,
        )

    def _payload(self, *, request: FrozenRunRequest, prompt: str) -> dict[str, object]:
        width, height = request.settings.width, request.settings.height
        if (
            width % 16
            or height % 16
            or max(width, height) > 3840
            or max(width, height) > 3 * min(width, height)
            or not 655360 <= width * height <= 8294400
        ):
            raise ProviderContractError(
                "GPT Image needs multiples of 16, 0.66–8.29 MP, "
                "at most 3840px per edge and a 3:1 aspect ratio"
            )
        return {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "quality": request.settings.image_quality,
            "num_images": 1,
            "output_format": "png",
        }

    def _upload(self, url: str) -> str:
        image = self._reader.read(url)
        return self._transport.upload(content=image.content, filename=image.filename)

    @staticmethod
    def _owns(model: str, endpoint: str) -> bool:
        return any(
            model == f"gpt-image-2.5-{variant}"
            and endpoint
            in {
                f"openai/gpt-image-2.5/{variant}/text-to-image",
                f"openai/gpt-image-2.5/{variant}/edit",
            }
            for variant in ("flare", "sunburst")
        )

    def submit(self, request: PreparedProviderRequest) -> ProviderJob:
        if request.provider != self.id or not self._owns(
            request.model, request.endpoint
        ):
            raise ProviderContractError(
                "The prepared request does not belong to this provider"
            )
        request_id = self._transport.submit(
            endpoint=request.endpoint, payload=request.request_payload
        )
        return ProviderJob(
            request.provider,
            request.model,
            request.endpoint,
            request_id,
            request.request_payload,
        )

    def result(self, job: ProviderJob) -> ProviderResult:
        if job.provider != self.id or not self._owns(job.model, job.endpoint):
            raise ProviderContractError("The job does not belong to this provider")
        response = self._transport.result(
            endpoint=job.endpoint, request_id=job.request_id
        )
        images = response.get("images")
        if (
            not isinstance(images, list)
            or len(images) != 1
            or not isinstance(images[0], dict)
        ):
            raise ProviderContractError(
                "Image provider must return exactly one output image"
            )
        image = images[0]
        url = image.get("url")
        if not isinstance(url, str) or not url:
            raise ProviderContractError("Output image is missing its URL")
        content_type = image.get("content_type", "image/png")
        if not isinstance(content_type, str):
            raise ProviderContractError("Invalid output content type")
        width, height = image.get("width"), image.get("height")
        return ProviderResult(
            job,
            url,
            content_type,
            width if isinstance(width, int) else None,
            height if isinstance(height, int) else None,
            response,
        )
