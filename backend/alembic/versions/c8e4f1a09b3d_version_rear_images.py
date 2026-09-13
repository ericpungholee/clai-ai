"""Store per-version rear views and freeze them into mesh jobs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c8e4f1a09b3d"
down_revision = "0f7d4b2a91ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "version_rear_images",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_url", sa.String(length=2048)),
        sa.Column("artifact_storage_key", sa.String(length=2048)),
        sa.Column("artifact_sha256", sa.String(length=64)),
        sa.Column("artifact_content_type", sa.String(length=120)),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="dispatching",
        ),
        sa.Column("error", sa.Text()),
        sa.Column("source_artifact_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "request_payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("provider", sa.String(length=64)),
        sa.Column("model", sa.String(length=160)),
        sa.Column("endpoint", sa.String(length=240)),
        sa.Column("provider_request_id", sa.String(length=240)),
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
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'dispatching', 'provider_pending', "
            "'ingesting', 'complete', 'failed')",
            name="ck_version_rear_images_status",
        ),
        sa.CheckConstraint(
            "status <> 'complete' OR artifact_url IS NOT NULL",
            name="ck_version_rear_images_complete_artifact",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["versions.id"],
            name="fk_version_rear_images_version_id_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("version_id", name="pk_version_rear_images"),
    )
    op.add_column(
        "version_meshes",
        sa.Column("source_rear_artifact_url", sa.String(length=2048)),
    )


def downgrade() -> None:
    op.drop_column("version_meshes", "source_rear_artifact_url")
    op.drop_table("version_rear_images")
