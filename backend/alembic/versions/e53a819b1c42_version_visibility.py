"""Keep strip visibility separate from immutable versions."""

from alembic import op
import sqlalchemy as sa

revision = "e53a819b1c42"
down_revision = "d4b21c6e092a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "version_visibility",
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("versions.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "hidden_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("version_visibility")
