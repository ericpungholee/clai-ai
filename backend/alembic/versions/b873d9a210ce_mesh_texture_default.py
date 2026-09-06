"""Default new mesh jobs to image textures; retain legacy cache labels."""

from alembic import op

revision = "b873d9a210ce"
down_revision = "a762c048db15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("version_meshes", "texture", server_default="standard")


def downgrade() -> None:
    op.alter_column("version_meshes", "texture", server_default="no")
