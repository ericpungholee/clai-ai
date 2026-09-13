from app.domain.runs import Op

PRESERVATION_PREAMBLE = (
    "This is an edit of the attached image. Keep the same object and the same\n"
    "photograph: same camera angle and same framing.\n"
    "{background_instruction}"
    "Keep every attribute the instruction does not mention.\n"
    "The instruction may change any attribute it names, including form,\n"
    "proportions, colour, material, and finish. Apply it fully.\n\n"
    "Instruction: {resolved_user_prompt}"
)

EDIT_OPS = frozenset(
    {
        Op.EDIT_INSTRUCT,
        Op.EDIT_INPAINT,
        Op.EDIT_COMPOSITE,
        Op.EDIT_REF_GUIDED,
    }
)

GENERATE_OPS = frozenset({Op.GENERATE, Op.GENERATE_REF})


class PromptBuildError(ValueError):
    pass


def build_prompt(*, user_prompt: str, op: Op, white_background: bool = True) -> str:
    resolved_prompt = user_prompt.strip()
    if not resolved_prompt:
        raise PromptBuildError("A run prompt cannot be empty")
    if op in EDIT_OPS:
        prompt = PRESERVATION_PREAMBLE.format(
            background_instruction=""
            if white_background
            else "Keep the same background.\n",
            resolved_user_prompt=resolved_prompt,
        )
        if white_background and op != Op.EDIT_INPAINT:
            return f"{prompt}\n\nThe background must be plain pure white."
        return prompt
    if op in GENERATE_OPS:
        background = (
            "Photograph the product on a pure white background with "
            if white_background
            else "Use "
        )
        return (
            f"Create a professional studio product photograph of {resolved_prompt}, "
            "shot from a front view at eye level, perfectly centered. "
            f"{background}professional studio lighting that creates soft, subtle "
            "shadows. Use sharp focus to capture clear, well-defined edges. "
            "Center the product in the frame and fill the frame while ensuring "
            "the entire product is visible - nothing should be cropped or cut off. "
            "The design should be consistent and suitable for viewing from "
            "multiple camera angles. Avoid any text overlays, watermarks, "
            "or distracting elements. Product graphics, printed text and logos are "
            "part of the design and must remain legible. Show only the requested "
            "object and components: do not assemble accessories or category-associated "
            "parts. Missing components are intentional; do not complete an assembly."
        )
    return resolved_prompt
