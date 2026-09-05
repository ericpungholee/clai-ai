from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class Op(StrEnum):
    GENERATE = "generate"
    GENERATE_REF = "generate_ref"
    EDIT_INSTRUCT = "edit_instruct"
    EDIT_INPAINT = "edit_inpaint"
    EDIT_COMPOSITE = "edit_composite"
    EDIT_REF_GUIDED = "edit_ref_guided"


class EdgeRole(StrEnum):
    SUBJECT = "subject"
    CONNECT = "connect"


@dataclass(frozen=True)
class VersionPin:
    mode: Literal["version"] = field(default="version", init=False)
    version_id: str


@dataclass(frozen=True)
class ActivePin:
    mode: Literal["active"] = field(default="active", init=False)


@dataclass(frozen=True)
class SubjectEdge:
    id: str
    source_node_id: str
    target_node_id: str
    pin: VersionPin
    role: Literal[EdgeRole.SUBJECT] = field(default=EdgeRole.SUBJECT, init=False)


@dataclass(frozen=True)
class ConnectEdge:
    id: str
    source_node_id: str
    target_node_id: str
    pin: ActivePin
    order: int
    role: Literal[EdgeRole.CONNECT] = field(default=EdgeRole.CONNECT, init=False)


type RunEdge = SubjectEdge | ConnectEdge


@dataclass(frozen=True)
class MaskSnapshot:
    rle: str
    width: int
    height: int
    subject_version_id: str

    def __post_init__(self) -> None:
        if not self.rle:
            raise ValueError("Mask RLE cannot be empty")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Mask dimensions must be positive")


@dataclass(frozen=True)
class NodeSettings:
    aspect_ratio: str = "1:1"
    width: int = 1024
    height: int = 1024
    white_background: bool = True

    def __post_init__(self) -> None:
        if not self.aspect_ratio.strip():
            raise ValueError("Aspect ratio cannot be empty")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Resolution must be positive")


@dataclass(frozen=True)
class NodeSnapshot:
    id: str
    prompt: str
    settings: NodeSettings = field(default_factory=NodeSettings)
    seed: int | None = None
    mask: MaskSnapshot | None = None
    active_version_id: str | None = None


@dataclass(frozen=True)
class VersionSnapshot:
    id: str
    node_id: str
    artifact_url: str
    seed: int
    edit_depth: int

    def __post_init__(self) -> None:
        if self.edit_depth < 0:
            raise ValueError("Edit depth cannot be negative")


@dataclass(frozen=True)
class ResolvedInputs:
    node: NodeSnapshot
    subject: VersionSnapshot | None
    connects: tuple[VersionSnapshot, ...]
    mask: MaskSnapshot | None
    seed: int


@dataclass(frozen=True)
class InputSnapshot:
    subject_version_id: str | None
    connect_version_ids: tuple[str, ...]
    mask_hash: str | None


@dataclass(frozen=True)
class FrozenRunRequest:
    node_id: str
    op: Op
    prompt_at_runtime: str
    seed: int
    settings: NodeSettings
    subject: VersionSnapshot | None
    connects: tuple[VersionSnapshot, ...]
    mask: MaskSnapshot | None
    input_snapshot: InputSnapshot
    edit_depth: int
    user_prompt: str = ""
    run_signature: str | None = None
