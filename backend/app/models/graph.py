import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        CheckConstraint(
            "type IN ('prompt', 'image', 'model3d')",
            name="ck_graph_nodes_type",
        ),
        UniqueConstraint(
            "project_id",
            "id",
            name="uq_graph_nodes_project_id_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    type: Mapped[str] = mapped_column(String(32))
    position_x: Mapped[float] = mapped_column(Float)
    position_y: Mapped[float] = mapped_column(Float)
    data: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_graph_edges_source_node",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_graph_edges_target_node",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    target_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    source_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
