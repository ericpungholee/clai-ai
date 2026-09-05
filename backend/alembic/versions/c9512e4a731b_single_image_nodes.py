"""Retire image visibility and restore retained images on older canvases."""

from alembic import op
import sqlalchemy as sa

revision = "c9512e4a731b"
down_revision = "b873d9a210ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older Hide actions could leave a node without a presented image. Keep every
    # image on its original node and present the newest when no choice exists.
    op.execute("""
        UPDATE graph_nodes
        SET active_version_id = (
            SELECT id FROM versions WHERE versions.node_id = graph_nodes.id
            ORDER BY created_at DESC, id DESC LIMIT 1
        )
        WHERE active_version_id IS NULL
          AND EXISTS (SELECT 1 FROM versions WHERE versions.node_id = graph_nodes.id)
    """)
    op.drop_table("version_visibility")


def downgrade() -> None:
    # Visibility preferences were retired; image artifacts are never removed.
    op.create_table(
        "version_visibility",
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey("versions.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
