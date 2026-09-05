import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domain.prompts import PromptPart

json_type = JSON().with_variant(JSONB, "postgresql")


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_graph_nodes_project_id_id"),
        ForeignKeyConstraint(
            ["id", "active_version_id"],
            ["versions.node_id", "versions.id"],
            name="fk_graph_nodes_active_version",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["mask_subject_version_id"],
            ["versions.id"],
            name="fk_graph_nodes_mask_subject_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "mask_rle IS NULL OR "
            "(mask_width > 0 AND mask_height > 0 "
            "AND mask_subject_version_id IS NOT NULL)",
            name="ck_graph_nodes_mask_complete",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), default="Untitled concept")
    prompt: Mapped[list[PromptPart]] = mapped_column(json_type, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    settings: Mapped[dict[str, object]] = mapped_column(
        json_type,
        default=lambda: {
            "aspect_ratio": "1:1",
            "width": 1024,
            "height": 1024,
            "whiteBackground": True,
        },
    )
    seed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mask_rle: Mapped[str | None] = mapped_column(Text, nullable=True)
    mask_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mask_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mask_subject_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    position_x: Mapped[float] = mapped_column(Float)
    position_y: Mapped[float] = mapped_column(Float)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Version(Base):
    __tablename__ = "versions"
    __table_args__ = (
        UniqueConstraint("node_id", "id", name="uq_versions_node_id_id"),
        UniqueConstraint("run_job_id", name="uq_versions_run_job_id"),
        CheckConstraint(
            "op IN ('generate', 'generate_ref', 'edit_instruct', "
            "'edit_inpaint', 'edit_composite', 'edit_ref_guided')",
            name="ck_versions_op",
        ),
        CheckConstraint("edit_depth >= 0", name="ck_versions_edit_depth"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("graph_nodes.id", ondelete="RESTRICT"),
        index=True,
    )
    run_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "run_jobs.id",
            name="fk_versions_run_job_id_run_jobs",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    artifact_url: Mapped[str] = mapped_column(String(2048))
    artifact_storage_key: Mapped[str] = mapped_column(String(2048))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    artifact_content_type: Mapped[str] = mapped_column(String(120))
    op: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(160))
    endpoint: Mapped[str] = mapped_column(String(240))
    params: Mapped[dict[str, object]] = mapped_column(json_type)
    provider_response_metadata: Mapped[dict[str, object]] = mapped_column(json_type)
    seed: Mapped[int] = mapped_column(BigInteger)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(json_type)
    prompt_at_runtime: Mapped[str] = mapped_column(Text)
    edit_depth: Mapped[int] = mapped_column(Integer)


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        CheckConstraint(
            "source_node_id <> target_node_id", name="ck_graph_edges_no_self"
        ),
        Index(
            "uq_graph_edges_connect_source",
            "target_node_id",
            "source_node_id",
            unique=True,
            postgresql_where=text("role = 'connect'"),
            sqlite_where=text("role = 'connect'"),
        ),
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
        ForeignKeyConstraint(
            ["source_node_id", "pinned_version_id"],
            ["versions.node_id", "versions.id"],
            name="fk_graph_edges_pinned_source_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(role = 'subject' AND pin_mode = 'version' "
            "AND pinned_version_id IS NOT NULL AND connect_order IS NULL) OR "
            "(role = 'connect' AND pin_mode = 'active' "
            "AND pinned_version_id IS NULL AND connect_order IS NOT NULL "
            "AND connect_order >= 0)",
            name="ck_graph_edges_role_pin",
        ),
        UniqueConstraint(
            "target_node_id",
            "connect_order",
            name="uq_graph_edges_target_connect_order",
        ),
        Index(
            "uq_graph_edges_one_subject_per_target",
            "target_node_id",
            unique=True,
            postgresql_where=text("role = 'subject'"),
            sqlite_where=text("role = 'subject'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    target_node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    role: Mapped[str] = mapped_column(String(16))
    pin_mode: Mapped[str] = mapped_column(String(16))
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    connect_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VersionMetric(Base):
    __tablename__ = "version_metrics"
    __table_args__ = (
        CheckConstraint(
            "op IN ('generate', 'generate_ref', 'edit_instruct', "
            "'edit_inpaint', 'edit_composite', 'edit_ref_guided')",
            name="ck_version_metrics_op",
        ),
        CheckConstraint(
            "status IN ('pending', 'complete', 'failed')",
            name="ck_version_metrics_status",
        ),
        CheckConstraint(
            "change_magnitude IS NULL OR "
            "(change_magnitude >= 0 AND change_magnitude <= 1)",
            name="ck_version_metrics_magnitude",
        ),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    op: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(120), default="dinov2_cosine")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    change_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VersionVisibility(Base):
    __tablename__ = "version_visibility"

    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("versions.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    hidden_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VersionMesh(Base):
    __tablename__ = "version_meshes"

    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(160))
    artifact_url: Mapped[str] = mapped_column(String(2048))
    provider_response_metadata: Mapped[dict[str, object]] = mapped_column(json_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RunJob(Base):
    __tablename__ = "run_jobs"
    __table_args__ = (
        UniqueConstraint(
            "node_id", "idempotency_key", name="uq_run_jobs_node_id_idempotency"
        ),
        CheckConstraint(
            "status IN ('queued', 'dispatching', 'provider_pending', "
            "'ingesting', 'complete', 'failed')",
            name="ck_run_jobs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_run_jobs_attempts"),
        ForeignKeyConstraint(
            ["project_id", "node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_run_jobs_node",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        index=True,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    frozen_request: Mapped[dict[str, object]] = mapped_column(json_type)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(240), nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    provider_request_payload: Mapped[dict[str, object] | None] = mapped_column(
        json_type, nullable=True
    )
    provider_response_metadata: Mapped[dict[str, object] | None] = mapped_column(
        json_type, nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
