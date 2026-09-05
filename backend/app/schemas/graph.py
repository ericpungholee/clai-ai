import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, JsonValue, StringConstraints

from app.domain.runs import Op

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class GraphPosition(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class NodeSettingsData(BaseModel):
    aspect_ratio: str = Field(default="1:1", min_length=1, max_length=16)
    width: int = Field(default=1024, ge=1, le=4096)
    height: int = Field(default=1024, ge=1, le=4096)
    whiteBackground: bool = True


class VersionData(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    created_at: datetime
    artifact_url: str
    op: Op
    provider: str
    model: str
    endpoint: str
    params: dict[str, JsonValue]
    seed: int
    input_snapshot: dict[str, JsonValue]
    prompt_at_runtime: str
    edit_depth: int
    hidden: bool = False
    branch_node_ids: list[uuid.UUID] = Field(default_factory=list)
    masked_outside_change: float | None = None


class MaskData(BaseModel):
    rle: str = Field(min_length=1, max_length=16000000)
    width: int = Field(ge=1, le=4096)
    height: int = Field(ge=1, le=4096)
    subject_version_id: uuid.UUID


class PromptTextData(BaseModel):
    type: Literal["text"]
    text: str = Field(max_length=8000)


class PromptConnectData(BaseModel):
    type: Literal["connect"]
    edge_id: uuid.UUID
    source_node_id: uuid.UUID


PromptPartData = Annotated[
    PromptTextData | PromptConnectData, Field(discriminator="type")
]


class PromptUpdate(BaseModel):
    document: list[PromptPartData] = Field(max_length=128)
    expected_revision: int = Field(ge=0)


class GraphNodeData(BaseModel):
    id: uuid.UUID
    title: str
    prompt: str
    settings: NodeSettingsData
    seed: int | None
    active_version_id: uuid.UUID | None
    position: GraphPosition
    versions: list[VersionData]
    mask: MaskData | None = None
    document: list[PromptPartData]
    revision: int
    deleted: bool = False
    run: "RunJobData | None" = None


class VersionPinData(BaseModel):
    mode: Literal["version"] = "version"
    version_id: uuid.UUID


class ActivePinData(BaseModel):
    mode: Literal["active"] = "active"


PinData = Annotated[VersionPinData | ActivePinData, Field(discriminator="mode")]


class SubjectEdgeData(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    role: Literal["subject"] = "subject"
    pin: VersionPinData
    order: None = None


class ConnectEdgeData(BaseModel):
    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    role: Literal["connect"] = "connect"
    pin: ActivePinData
    order: int


GraphEdgeData = Annotated[
    SubjectEdgeData | ConnectEdgeData, Field(discriminator="role")
]


class GraphDocument(BaseModel):
    nodes: list[GraphNodeData]
    edges: list[GraphEdgeData]


class NodeCreate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: Title = "Untitled concept"
    prompt: str = Field(default="", max_length=8000)
    settings: NodeSettingsData = Field(default_factory=NodeSettingsData)
    seed: int | None = None
    position: GraphPosition


class NodeUpdate(BaseModel):
    expected_revision: int | None = Field(default=None, ge=0)
    title: Title | None = None
    prompt: str | None = Field(default=None, max_length=8000)
    settings: NodeSettingsData | None = None
    seed: int | None = None
    active_version_id: uuid.UUID | None = None
    position: GraphPosition | None = None


class SubjectEdgeReplace(BaseModel):
    source_node_id: uuid.UUID
    version_id: uuid.UUID


class BranchCreate(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: Title = "Untitled concept"
    prompt: str = Field(default="", max_length=8000)
    settings: NodeSettingsData = Field(default_factory=NodeSettingsData)
    position: GraphPosition


class BranchData(BaseModel):
    node: GraphNodeData
    edge: GraphEdgeData


class RunPreviewData(BaseModel):
    op: Op


class RunSubmit(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)


class RunJobData(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    status: Literal[
        "queued",
        "dispatching",
        "provider_pending",
        "ingesting",
        "complete",
        "failed",
    ]
    op: Op
    attempts: int
    error: str | None
    version_id: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None
