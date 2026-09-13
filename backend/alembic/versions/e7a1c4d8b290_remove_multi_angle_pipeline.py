"""Remove the retired multi-angle image and mesh fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e7a1c4d8b290"
down_revision = "d2b9a71f403e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("version_image_views")
    op.drop_column("version_meshes", "source_image_urls")


def downgrade() -> None:
    op.add_column(
        "version_meshes",
        sa.Column(
            "source_image_urls",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE version_meshes SET source_image_urls =
        CASE WHEN source_artifact_url IS NULL THEN '[]'::jsonb
             ELSE jsonb_build_array(source_artifact_url) END
        """
    )
    op.create_table(
        "version_image_views",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("angle", sa.String(16), nullable=False),
        sa.Column("artifact_url", sa.String(2048)),
        sa.Column("artifact_storage_key", sa.String(2048)),
        sa.Column("artifact_sha256", sa.String(64)),
        sa.Column("artifact_content_type", sa.String(120)),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column("source_artifact_url", sa.String(2048), nullable=False),
        sa.Column(
            "request_payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(160)),
        sa.Column("endpoint", sa.String(240)),
        sa.Column("provider_request_id", sa.String(240)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "angle IN ('right', 'back', 'left')",
            name="ck_version_image_views_angle",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'dispatching', 'provider_pending', "
            "'ingesting', 'complete', 'failed')",
            name="ck_version_image_views_status",
        ),
        sa.CheckConstraint(
            "status <> 'complete' OR artifact_url IS NOT NULL",
            name="ck_version_image_views_complete_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_version_image_views_version_id_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", "angle", name="pk_version_image_views"),
    )
