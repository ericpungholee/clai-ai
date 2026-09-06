"""Remove projects from the home page without erasing version history."""

from alembic import op
import sqlalchemy as sa

revision = "a762c048db15"
down_revision = "f625a18798ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE projects SET thumbnail_url = latest.artifact_url FROM (SELECT DISTINCT ON (n.project_id) n.project_id, v.artifact_url FROM versions v JOIN graph_nodes n ON n.id = v.node_id ORDER BY n.project_id, v.created_at DESC, v.id DESC) latest WHERE latest.project_id = projects.id"
    )


def downgrade() -> None:
    op.drop_column("projects", "deleted_at")
