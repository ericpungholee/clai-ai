from app.domain.runs import Op

PRESERVATION_PREAMBLE = (
    "Preserve exactly every unmentioned attribute, including geometry,\n"
    "proportions, silhouette, camera angle, framing, lighting direction,\n"
    "and background.\n"
    "Change only: {resolved_user_prompt}\n"
    "Do not restyle or reinterpret any other element."
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
