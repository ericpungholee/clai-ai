from app.domain.runs import Op

PRESERVATION_PREAMBLE = (
    "This is an edit of the attached image. Keep the same object and the same\n"
    "photograph: same camera angle, same framing, same background.\n"
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
WHITE_BACKGROUND_CLAUSE = "Place the object on a clean white background."


class PromptBuildError(ValueError):
    pass


def build_prompt(*, user_prompt: str, op: Op, white_background: bool = True) -> str:
    resolved_prompt = user_prompt.strip()
    if not resolved_prompt:
        raise PromptBuildError("A run prompt cannot be empty")
    if op in EDIT_OPS:
        return PRESERVATION_PREAMBLE.format(resolved_user_prompt=resolved_prompt)
    if op in GENERATE_OPS and white_background:
        return f"{resolved_prompt}\n\n{WHITE_BACKGROUND_CLAUSE}"
    return resolved_prompt
