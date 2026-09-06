"""Remove output measurements and retain coarse run timings."""

from alembic import op
import sqlalchemy as sa

revision = "0f7d4b2a91ce"
down_revision = "c9512e4a731b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("version_metrics")
    op.add_column("run_jobs", sa.Column("provider_elapsed_seconds", sa.Float()))
    op.add_column("run_jobs", sa.Column("total_elapsed_seconds", sa.Float()))


def downgrade() -> None:
    op.drop_column("run_jobs", "total_elapsed_seconds")
    op.drop_column("run_jobs", "provider_elapsed_seconds")
    op.create_table(
        "version_metrics",
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("op", sa.String(32), nullable=False),
        sa.Column(
            "method",
            sa.String(120),
            nullable=False,
            server_default="dinov2_cosine",
        ),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column("change_magnitude", sa.Float()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
