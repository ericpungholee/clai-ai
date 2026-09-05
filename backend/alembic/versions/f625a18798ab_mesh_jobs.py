"""Version-scoped derived mesh cache and durable generation state."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f625a18798ab"
down_revision = "e53a819b1c42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("version_meshes", "artifact_url", nullable=True)
    for column in [
        sa.Column("preview_url", sa.String(2048)),
        sa.Column("status", sa.String(32), nullable=False, server_default="complete"),
        sa.Column("texture", sa.String(16), nullable=False, server_default="no"),
        sa.Column(
            "attempt_id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source_artifact_url", sa.String(2048)),
        sa.Column(
            "request_payload",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("provider_request_id", sa.String(240)),
        sa.Column("error", sa.Text()),
        sa.Column("elapsed_seconds", sa.Float()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
    ]:
        op.add_column("version_meshes", column)
    op.create_check_constraint(
        "ck_version_meshes_status",
        "version_meshes",
        "status IN ('queued', 'dispatching', 'provider_pending', 'ingesting', 'complete', 'failed')",
    )
    op.create_check_constraint(
        "ck_version_meshes_texture", "version_meshes", "texture IN ('no', 'standard')"
    )
    op.create_check_constraint(
        "ck_version_meshes_complete_artifact",
        "version_meshes",
        "status <> 'complete' OR artifact_url IS NOT NULL",
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM version_meshes WHERE artifact_url IS NULL) THEN RAISE EXCEPTION 'Unfinished mesh jobs must be resolved before downgrading'; END IF; END $$"
    )
    for name in ("status", "texture", "complete_artifact"):
        op.drop_constraint(f"ck_version_meshes_{name}", "version_meshes", type_="check")
    for name in (
        "preview_url",
        "status",
        "texture",
        "attempt_id",
        "source_artifact_url",
        "request_payload",
        "provider_request_id",
        "error",
        "elapsed_seconds",
        "started_at",
    ):
        op.drop_column("version_meshes", name)
    op.alter_column("version_meshes", "artifact_url", nullable=False)
