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


class PromptBuildError(ValueError):
    pass


def build_prompt(*, user_prompt: str, op: Op) -> str:
    resolved_prompt = user_prompt.strip()
    if not resolved_prompt:
        raise PromptBuildError("A run prompt cannot be empty")
    if op not in EDIT_OPS:
        return resolved_prompt
    return PRESERVATION_PREAMBLE.format(resolved_user_prompt=resolved_prompt)
