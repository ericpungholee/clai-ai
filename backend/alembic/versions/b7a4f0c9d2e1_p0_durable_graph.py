from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7a4f0c9d2e1"
down_revision: str | Sequence[str] | None = "31d1d8b844ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")

    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("settings", jsonb(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=True),
        sa.Column("mask_rle", sa.Text(), nullable=True),
        sa.Column("mask_width", sa.Integer(), nullable=True),
        sa.Column("mask_height", sa.Integer(), nullable=True),
        sa.Column("mask_base_version_id", sa.Uuid(), nullable=True),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mask_rle IS NULL OR "
            "(mask_width > 0 AND mask_height > 0 AND mask_base_version_id IS NOT NULL)",
            name="ck_graph_nodes_mask_complete",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_graph_nodes_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_graph_nodes"),
        sa.UniqueConstraint(
            "project_id", "id", name="uq_graph_nodes_project_id_id"
        ),
    )
    op.create_index("ix_graph_nodes_project_id", "graph_nodes", ["project_id"])

    op.create_table(
        "run_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("frozen_request", jsonb(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("endpoint", sa.String(length=240), nullable=True),
        sa.Column("provider_request_id", sa.String(length=240), nullable=True),
        sa.Column("provider_request_payload", jsonb(), nullable=True),
        sa.Column("provider_response_metadata", jsonb(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_run_jobs_attempts"),
        sa.CheckConstraint(
            "status IN ('queued', 'dispatching', 'provider_pending', "
            "'ingesting', 'complete', 'failed')",
            name="ck_run_jobs_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_run_jobs_node",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_run_jobs_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_jobs"),
        sa.UniqueConstraint(
            "node_id", "idempotency_key", name="uq_run_jobs_node_id_idempotency"
        ),
    )
    op.create_index("ix_run_jobs_node_id", "run_jobs", ["node_id"])
    op.create_index("ix_run_jobs_project_id", "run_jobs", ["project_id"])

    op.create_table(
        "versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=False),
        sa.Column("run_job_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("artifact_url", sa.String(length=2048), nullable=False),
        sa.Column("artifact_storage_key", sa.String(length=2048), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_content_type", sa.String(length=120), nullable=False),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("endpoint", sa.String(length=240), nullable=False),
        sa.Column("params", jsonb(), nullable=False),
        sa.Column("provider_response_metadata", jsonb(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("input_snapshot", jsonb(), nullable=False),
        sa.Column("prompt_at_runtime", sa.Text(), nullable=False),
        sa.Column("edit_depth", sa.Integer(), nullable=False),
        sa.CheckConstraint("edit_depth >= 0", name="ck_versions_edit_depth"),
        sa.CheckConstraint(
            "op IN ('generate', 'generate_ref', 'edit_instruct', "
            "'edit_inpaint', 'edit_composite', 'edit_ref_guided')",
            name="ck_versions_op",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["graph_nodes.id"],
            name="fk_versions_node_id_graph_nodes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_job_id"],
            ["run_jobs.id"],
            name="fk_versions_run_job_id_run_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_versions"),
        sa.UniqueConstraint("node_id", "id", name="uq_versions_node_id_id"),
        sa.UniqueConstraint("run_job_id", name="uq_versions_run_job_id"),
    )
    op.create_index("ix_versions_node_id", "versions", ["node_id"])

    op.create_foreign_key(
        "fk_graph_nodes_active_version",
        "graph_nodes",
        "versions",
        ["id", "active_version_id"],
        ["node_id", "id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_graph_nodes_mask_base_version",
        "graph_nodes",
        "versions",
        ["mask_base_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("pin_mode", sa.String(length=16), nullable=False),
        sa.Column("pinned_version_id", sa.Uuid(), nullable=True),
        sa.Column("connect_order", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(role = 'base' AND pin_mode = 'version' "
            "AND pinned_version_id IS NOT NULL AND connect_order IS NULL) OR "
            "(role = 'connect' AND pin_mode = 'active' "
            "AND pinned_version_id IS NULL AND connect_order IS NOT NULL "
            "AND connect_order >= 0)",
            name="ck_graph_edges_role_pin",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_graph_edges_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_graph_edges_source_node",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            name="fk_graph_edges_target_node",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id", "pinned_version_id"],
            ["versions.node_id", "versions.id"],
            name="fk_graph_edges_pinned_source_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_graph_edges"),
        sa.UniqueConstraint(
            "target_node_id",
            "connect_order",
            name="uq_graph_edges_target_connect_order",
        ),
    )
    op.create_index("ix_graph_edges_project_id", "graph_edges", ["project_id"])
    op.create_index(
        "uq_graph_edges_one_base_per_target",
        "graph_edges",
        ["target_node_id"],
        unique=True,
        postgresql_where=sa.text("role = 'base'"),
    )

    op.create_table(
        "version_metrics",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("op", sa.String(length=32), nullable=False),
        sa.Column("method", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("change_magnitude", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change_magnitude IS NULL OR "
            "(change_magnitude >= 0 AND change_magnitude <= 1)",
            name="ck_version_metrics_magnitude",
        ),
        sa.CheckConstraint(
            "op IN ('generate', 'generate_ref', 'edit_instruct', "
            "'edit_inpaint', 'edit_composite', 'edit_ref_guided')",
            name="ck_version_metrics_op",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'complete', 'failed')",
            name="ck_version_metrics_status",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_version_metrics_version_id_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_version_metrics"),
    )

    op.create_table(
        "version_meshes",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("artifact_url", sa.String(length=2048), nullable=False),
        sa.Column("provider_response_metadata", jsonb(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_version_meshes_version_id_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_version_meshes"),
    )

    op.execute(
        """
        CREATE FUNCTION clai_reject_version_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'versions are insert-only'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER versions_insert_only
        BEFORE UPDATE OR DELETE ON versions
        FOR EACH ROW EXECUTE FUNCTION clai_reject_version_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION clai_enforce_connect_cap()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            connect_count integer;
        BEGIN
            IF NEW.role <> 'connect' THEN
                RETURN NEW;
            END IF;

            PERFORM 1 FROM graph_nodes
            WHERE id = NEW.target_node_id
            FOR UPDATE;

            SELECT count(*) INTO connect_count
            FROM graph_edges
            WHERE target_node_id = NEW.target_node_id
              AND role = 'connect'
              AND id <> NEW.id;

            IF connect_count >= 2 THEN
                RAISE EXCEPTION 'a node accepts at most two connect edges'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER graph_edges_connect_cap
        BEFORE INSERT OR UPDATE OF target_node_id, role ON graph_edges
        FOR EACH ROW EXECUTE FUNCTION clai_enforce_connect_cap()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER graph_edges_connect_cap ON graph_edges")
    op.execute("DROP FUNCTION clai_enforce_connect_cap()")
    op.drop_table("version_meshes")
    op.drop_table("version_metrics")
    op.drop_table("graph_edges")
    op.execute("DROP TRIGGER versions_insert_only ON versions")
    op.execute("DROP FUNCTION clai_reject_version_mutation()")
    op.drop_constraint(
        "fk_graph_nodes_mask_base_version", "graph_nodes", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_graph_nodes_active_version", "graph_nodes", type_="foreignkey"
    )
    op.drop_table("versions")
    op.drop_table("run_jobs")
    op.drop_table("graph_nodes")

    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("data", jsonb(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('prompt', 'image', 'model3d')", name="ck_graph_nodes_type"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id"),
    )
    op.create_index("ix_graph_nodes_project_id", "graph_nodes", ["project_id"])
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_node_id", sa.Uuid(), nullable=False),
        sa.Column("target_node_id", sa.Uuid(), nullable=False),
        sa.Column("source_handle", sa.String(length=120), nullable=True),
        sa.Column("target_handle", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "target_node_id"],
            ["graph_nodes.project_id", "graph_nodes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_edges_project_id", "graph_edges", ["project_id"])
