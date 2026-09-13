"""Expand saved rear views into version-scoped angle artifacts."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d2b9a71f403e"
down_revision = "c8e4f1a09b3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("version_rear_images", "version_image_views")
    op.add_column("version_image_views", sa.Column(
        "angle", sa.String(16), nullable=False, server_default="back"
    ))
    op.drop_constraint("pk_version_rear_images", "version_image_views", type_="primary")
    op.create_primary_key("pk_version_image_views", "version_image_views", ["version_id", "angle"])
    op.create_check_constraint("ck_version_image_views_angle", "version_image_views", "angle IN ('right', 'back', 'left')")
    for suffix in ("status", "complete_artifact"):
        op.execute(f"ALTER TABLE version_image_views RENAME CONSTRAINT ck_version_rear_images_{suffix} TO ck_version_image_views_{suffix}")
    op.alter_column("version_image_views", "angle", server_default=None)
    op.alter_column("version_image_views", "status", server_default="queued")
    op.add_column("version_meshes", sa.Column("source_image_urls", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.execute("""
        UPDATE version_meshes SET source_image_urls =
        CASE WHEN source_artifact_url IS NULL THEN '[]'::jsonb
             WHEN source_rear_artifact_url IS NULL THEN jsonb_build_array(source_artifact_url)
             ELSE jsonb_build_array(source_artifact_url, source_rear_artifact_url) END
    """)
    op.drop_column("version_meshes", "source_rear_artifact_url")


def downgrade() -> None:
    op.add_column("version_meshes", sa.Column("source_rear_artifact_url", sa.String(2048)))
    op.execute("""
        UPDATE version_meshes m SET source_rear_artifact_url = v.artifact_url
        FROM version_image_views v WHERE v.version_id = m.version_id
        AND v.angle = 'back' AND m.source_image_urls ? v.artifact_url
    """)
    op.drop_column("version_meshes", "source_image_urls")
    op.execute("DELETE FROM version_image_views WHERE angle <> 'back'")
    op.drop_constraint("ck_version_image_views_angle", "version_image_views", type_="check")
    op.drop_constraint("pk_version_image_views", "version_image_views", type_="primary")
    op.drop_column("version_image_views", "angle")
    op.create_primary_key("pk_version_rear_images", "version_image_views", ["version_id"])
    for suffix in ("status", "complete_artifact"):
        op.execute(f"ALTER TABLE version_image_views RENAME CONSTRAINT ck_version_image_views_{suffix} TO ck_version_rear_images_{suffix}")
    op.alter_column("version_image_views", "status", server_default="dispatching")
    op.rename_table("version_image_views", "version_rear_images")
