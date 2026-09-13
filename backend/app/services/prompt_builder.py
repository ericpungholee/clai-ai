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
WHITE_BACKGROUND_CLAUSE = "Place the object on a plain pure white background."
SINGLE_OBJECT_INSTRUCTION = (
    "Generate exactly one instance of the object in a single view. "
    "No duplicate objects, no side-by-side comparison, no contact sheet, "
    "and no multiple views."
)
ANGLE_VIEW_INSTRUCTION = (
    "Generate a separate image containing exactly one object: exactly one instance "
    "of the exact same object/design as the reference: the same physical object. "
    "Treat the reference "
    "image and original design specification as binding evidence. {viewpoint} "
    "Rotate the viewpoint only; keep the same object "
    "orientation, pose, scale, proportions, dimensions, materials, colors, style, "
    "silhouette, construction, and design details. Preserve all graphics, logos, "
    "lettering and their exact placement on the object's surfaces. Surface graphics "
    "must remain attached to their original surface and follow perspective and "
    "occlusion; never move, mirror, redraw, duplicate, or omit a visible graphic. "
    "If a graphic rotates out of view, do not paste it onto a newly visible face. "
    "For hidden areas, continue only materials and colors established by the reference "
    "or specification. Do not invent exposed layers, wood, grip tape, hardware, seams, "
    "textures, graphics, or construction details that are absent from both. "
    "Do not rotate, mirror, or redesign the object. "
    "Keep the entire object centered, at the same scale in the frame as the reference, "
    "and isolated on a plain simple background. Output only this one angle. "
    "No side-by-side comparison, no contact sheet, no multiple views, no duplicate "
    "objects, and no concatenated, stitched, tiled, or composite views.\n\n"
    "Original design specification:\n{design_prompt}"
)


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
        prompt = f"{resolved_prompt}\n\n{SINGLE_OBJECT_INSTRUCTION}"
        if white_background:
            return f"{prompt}\n\n{WHITE_BACKGROUND_CLAUSE}"
        return prompt
    return resolved_prompt


def build_angle_view_prompt(
    *, angle: str, design_prompt: str, white_background: bool = True
) -> str:
    viewpoints = {
        "right": "Orbit only the camera about 60 degrees toward the object's right "
        "side, producing a right-side three-quarter view at the same camera elevation.",
        "back": "Move only the camera 180 degrees around the object, viewing it "
        "directly from the opposite/rear side at the same camera elevation.",
        "left": "Orbit only the camera about 60 degrees toward the object's left side "
        "(opposite to the right view), producing a left-side three-quarter view at "
        "the same camera elevation.",
    }
    if angle not in viewpoints:
        raise PromptBuildError(f"Unsupported image angle: {angle}")
    resolved_design_prompt = design_prompt.strip()
    if not resolved_design_prompt:
        raise PromptBuildError("An angle view requires the original design prompt")
    prompt = ANGLE_VIEW_INSTRUCTION.format(
        viewpoint=viewpoints[angle], design_prompt=resolved_design_prompt
    )
    if white_background:
        return f"{prompt}\n\n{WHITE_BACKGROUND_CLAUSE}"
    return prompt
