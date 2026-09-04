from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f2a8d7e901"
down_revision: str | Sequence[str] | None = "b7a4f0c9d2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_graph_nodes_mask_base_version",
        "graph_nodes",
        type_="foreignkey",
    )
    op.alter_column(
        "graph_nodes",
        "mask_base_version_id",
        new_column_name="mask_subject_version_id",
    )
    op.create_foreign_key(
        "fk_graph_nodes_mask_subject_version",
        "graph_nodes",
        "versions",
        ["mask_subject_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("ck_graph_edges_role_pin", "graph_edges", type_="check")
    op.drop_index("uq_graph_edges_one_base_per_target", table_name="graph_edges")
    op.execute("UPDATE graph_edges SET role = 'subject' WHERE role = 'base'")
    op.create_check_constraint(
        "ck_graph_edges_role_pin",
        "graph_edges",
        "(role = 'subject' AND pin_mode = 'version' "
        "AND pinned_version_id IS NOT NULL AND connect_order IS NULL) OR "
        "(role = 'connect' AND pin_mode = 'active' "
        "AND pinned_version_id IS NULL AND connect_order IS NOT NULL "
        "AND connect_order >= 0)",
    )
    op.create_index(
        "uq_graph_edges_one_subject_per_target",
        "graph_edges",
        ["target_node_id"],
        unique=True,
        postgresql_where=sa.text("role = 'subject'"),
    )

    op.execute("ALTER TABLE versions DISABLE TRIGGER versions_insert_only")
    op.execute(
        """
        UPDATE versions
        SET input_snapshot = jsonb_set(
            input_snapshot - 'base_version_id',
            '{subject_version_id}',
            input_snapshot->'base_version_id',
            true
        )
        WHERE input_snapshot ? 'base_version_id'
        """
    )
    op.execute("ALTER TABLE versions ENABLE TRIGGER versions_insert_only")

    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request - 'base',
            '{subject}',
            frozen_request->'base',
            true
        )
        WHERE frozen_request ? 'base'
        """
    )
    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request,
            '{input_snapshot}',
            jsonb_set(
                (frozen_request->'input_snapshot') - 'base_version_id',
                '{subject_version_id}',
                frozen_request->'input_snapshot'->'base_version_id',
                true
            ),
            false
        )
        WHERE frozen_request->'input_snapshot' ? 'base_version_id'
        """
    )
    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request,
            '{mask}',
            jsonb_set(
                (frozen_request->'mask') - 'base_version_id',
                '{subject_version_id}',
                frozen_request->'mask'->'base_version_id',
                true
            ),
            false
        )
        WHERE frozen_request->'mask' ? 'base_version_id'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request,
            '{mask}',
            jsonb_set(
                (frozen_request->'mask') - 'subject_version_id',
                '{base_version_id}',
                frozen_request->'mask'->'subject_version_id',
                true
            ),
            false
        )
        WHERE frozen_request->'mask' ? 'subject_version_id'
        """
    )
    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request,
            '{input_snapshot}',
            jsonb_set(
                (frozen_request->'input_snapshot') - 'subject_version_id',
                '{base_version_id}',
                frozen_request->'input_snapshot'->'subject_version_id',
                true
            ),
            false
        )
        WHERE frozen_request->'input_snapshot' ? 'subject_version_id'
        """
    )
    op.execute(
        """
        UPDATE run_jobs
        SET frozen_request = jsonb_set(
            frozen_request - 'subject',
            '{base}',
            frozen_request->'subject',
            true
        )
        WHERE frozen_request ? 'subject'
        """
    )

    op.execute("ALTER TABLE versions DISABLE TRIGGER versions_insert_only")
    op.execute(
        """
        UPDATE versions
        SET input_snapshot = jsonb_set(
            input_snapshot - 'subject_version_id',
            '{base_version_id}',
            input_snapshot->'subject_version_id',
            true
        )
        WHERE input_snapshot ? 'subject_version_id'
        """
    )
    op.execute("ALTER TABLE versions ENABLE TRIGGER versions_insert_only")

    op.drop_index("uq_graph_edges_one_subject_per_target", table_name="graph_edges")
    op.drop_constraint("ck_graph_edges_role_pin", "graph_edges", type_="check")
    op.execute("UPDATE graph_edges SET role = 'base' WHERE role = 'subject'")
    op.create_check_constraint(
        "ck_graph_edges_role_pin",
        "graph_edges",
        "(role = 'base' AND pin_mode = 'version' "
        "AND pinned_version_id IS NOT NULL AND connect_order IS NULL) OR "
        "(role = 'connect' AND pin_mode = 'active' "
        "AND pinned_version_id IS NULL AND connect_order IS NOT NULL "
        "AND connect_order >= 0)",
    )
    op.create_index(
        "uq_graph_edges_one_base_per_target",
        "graph_edges",
        ["target_node_id"],
        unique=True,
        postgresql_where=sa.text("role = 'base'"),
    )

    op.drop_constraint(
        "fk_graph_nodes_mask_subject_version",
        "graph_nodes",
        type_="foreignkey",
    )
    op.alter_column(
        "graph_nodes",
        "mask_subject_version_id",
        new_column_name="mask_base_version_id",
    )
    op.create_foreign_key(
        "fk_graph_nodes_mask_base_version",
        "graph_nodes",
        "versions",
        ["mask_base_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
