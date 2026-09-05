from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d4b21c6e092a"
down_revision = "c3f2a8d7e901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only mutable node drafts change representation; version prompts stay exact.
    op.alter_column(
        "graph_nodes",
        "prompt",
        type_=JSONB(),
        postgresql_using="jsonb_build_array(jsonb_build_object('type', 'text', 'text', prompt))",
    )
    op.add_column(
        "graph_nodes",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_graph_edges_no_self", "graph_edges", "source_node_id <> target_node_id"
    )
    op.create_index(
        "uq_graph_edges_connect_source",
        "graph_edges",
        ["target_node_id", "source_node_id"],
        unique=True,
        postgresql_where=sa.text("role = 'connect'"),
    )


def downgrade() -> None:
    op.drop_index("uq_graph_edges_connect_source", table_name="graph_edges")
    op.drop_constraint("ck_graph_edges_no_self", "graph_edges", type_="check")
    op.drop_column("graph_nodes", "revision")
    # Do not erase chips during a downgrade: the structured drafts need this schema.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM graph_edges WHERE role = 'connect') THEN RAISE EXCEPTION 'Remove connect chips before downgrading'; END IF; END $$"
    )
    op.execute(
        "CREATE FUNCTION join_prompt_text(doc jsonb) RETURNS text LANGUAGE sql IMMUTABLE AS $$ SELECT coalesce(string_agg(part->>'text', '' ORDER BY ord), '') FROM jsonb_array_elements(doc) WITH ORDINALITY AS parts(part, ord) $$"
    )
    op.alter_column(
        "graph_nodes",
        "prompt",
        type_=sa.Text(),
        postgresql_using="join_prompt_text(prompt)",
    )
    op.execute("DROP FUNCTION join_prompt_text(jsonb)")
