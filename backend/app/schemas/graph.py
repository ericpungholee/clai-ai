import uuid
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, JsonValue, model_validator


class GraphNodeType(StrEnum):
    PROMPT = "prompt"
    IMAGE = "image"
    MODEL3D = "model3d"


class GraphPosition(BaseModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class GraphNodeData(BaseModel):
    id: uuid.UUID
    type: GraphNodeType
    position: GraphPosition
    data: dict[str, JsonValue] = Field(default_factory=dict)


class GraphEdgeData(BaseModel):
    id: uuid.UUID
    source: uuid.UUID
    target: uuid.UUID
    source_handle: str | None = Field(default=None, max_length=120)
    target_handle: str | None = Field(default=None, max_length=120)


class GraphDocument(BaseModel):
    nodes: list[GraphNodeData]
    edges: list[GraphEdgeData]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]

        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Node IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("Edge IDs must be unique")

        known_node_ids = set(node_ids)
        if any(
            edge.source not in known_node_ids or edge.target not in known_node_ids
            for edge in self.edges
        ):
            raise ValueError("Edge endpoints must reference nodes in the graph")

        return self
