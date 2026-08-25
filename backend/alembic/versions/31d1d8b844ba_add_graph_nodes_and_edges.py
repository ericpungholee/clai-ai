from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "31d1d8b844ba"
down_revision: str | Sequence[str] | None = "8b2b19d1243a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "type IN ('prompt', 'image', 'model3d')",
            name="ck_graph_nodes_type",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_graph_nodes_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_graph_nodes"),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_graph_nodes_project_id_id",
        ),
    )
    op.create_index(
        "ix_graph_nodes_project_id",
        "graph_nodes",
        ["project_id"],
    )

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
            ["project_id"],
            ["projects.id"],
            name="fk_graph_edges_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_graph_edges"),
    )
    op.create_index(
        "ix_graph_edges_project_id",
        "graph_edges",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_graph_edges_project_id", table_name="graph_edges")
    op.drop_table("graph_edges")
    op.drop_index("ix_graph_nodes_project_id", table_name="graph_nodes")
    op.drop_table("graph_nodes")
