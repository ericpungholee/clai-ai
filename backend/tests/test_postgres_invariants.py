import json
import os
import threading
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db
from app.main import app
from app.services.run_execution import execute_run_job
from app.services.run_queue import get_run_enqueuer
from tests.test_graph import (
    CapturingEnqueuer,
    FakeIngestor,
    FakeProvider,
)

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_engine() -> Generator[Engine, None, None]:
    base_url_value = os.getenv("TEST_DATABASE_URL")
    if not base_url_value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL invariant tests")
    base_url = make_url(base_url_value)
    database_name = f"clai_test_{uuid.uuid4().hex}"
    admin_engine = create_engine(base_url.set(database="postgres"))
    with admin_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))

    database_url = base_url.set(database=database_name)
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as connection:
            connection.execute(text(f'DROP DATABASE "{database_name}" WITH (FORCE)'))
        admin_engine.dispose()


def migrate(engine: Engine, revision: str = "head") -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.attributes["connection_url"] = engine.url.render_as_string(
        hide_password=False
    )
    command.upgrade(config, revision)


def insert_project(connection: object) -> uuid.UUID:
    project_id = uuid.uuid4()
    connection.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, 'Fixture')"),
        {"id": project_id},
    )
    return project_id


def insert_node(connection: object, project_id: uuid.UUID) -> uuid.UUID:
    node_id = uuid.uuid4()
    json_prompt = connection.scalar(
        text(
            "SELECT data_type = 'jsonb' FROM information_schema.columns "
            "WHERE table_name = 'graph_nodes' AND column_name = 'prompt'"
        )
    )
    prompt_value = "CAST(:prompt AS jsonb)" if json_prompt else ":prompt"
    connection.execute(
        text(
            f"""
            INSERT INTO graph_nodes (
                id, project_id, title, prompt, settings, position_x, position_y
            ) VALUES (
                :id, :project_id, 'Node', {prompt_value}, CAST(:settings AS jsonb), 0, 0
            )
            """
        ),
        {
            "id": node_id,
            "project_id": project_id,
            "prompt": json.dumps([{"type": "text", "text": "shoe"}])
            if json_prompt
            else "shoe",
            "settings": json.dumps(
                {"aspect_ratio": "1:1", "width": 1024, "height": 1024}
            ),
        },
    )
    return node_id


def insert_version(
    connection: object,
    project_id: uuid.UUID,
    node_id: uuid.UUID,
    *,
    input_snapshot: dict[str, object] | None = None,
    frozen_request: dict[str, object] | None = None,
    params: dict[str, object] | None = None,
    prompt_at_runtime: str = "shoe",
) -> uuid.UUID:
    job_id = uuid.uuid4()
    version_id = uuid.uuid4()
    frozen = json.dumps(frozen_request or {"node_id": str(node_id), "op": "generate"})
    connection.execute(
        text(
            """
            INSERT INTO run_jobs (
                id, project_id, node_id, idempotency_key, status,
                frozen_request, attempts
            ) VALUES (
                :id, :project_id, :node_id, :key, 'complete',
                CAST(:frozen AS jsonb), 1
            )
            """
        ),
        {
            "id": job_id,
            "project_id": project_id,
            "node_id": node_id,
            "key": str(job_id),
            "frozen": frozen,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO versions (
                id, node_id, run_job_id, artifact_url, artifact_storage_key,
                artifact_sha256, artifact_content_type, op, provider, model,
                endpoint, params, provider_response_metadata, seed,
                input_snapshot, prompt_at_runtime, edit_depth
            ) VALUES (
                :id, :node_id, :job_id, 'https://cdn.test/shoe.png',
                'shoe.png', :digest, 'image/png', 'generate', 'fake',
                'fixture-v1', 'fake/generate', CAST(:params AS jsonb),
                CAST('{}' AS jsonb), 42, CAST(:snapshot AS jsonb), :prompt, 0
            )
            """
        ),
        {
            "id": version_id,
            "node_id": node_id,
            "job_id": job_id,
            "digest": "a" * 64,
            "params": json.dumps(params or {}),
            "snapshot": json.dumps(
                input_snapshot
                or {
                    "subject_version_id": None,
                    "connect_version_ids": [],
                    "mask_hash": None,
                }
            ),
            "prompt": prompt_at_runtime,
        },
    )
    return version_id


def test_legacy_placeholder_rows_are_reset_but_projects_survive(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine, "31d1d8b844ba")
    project_id = uuid.uuid4()
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO projects (id, name) VALUES (:id, 'Keep me')"),
            {"id": project_id},
        )
        for node_id in (source_id, target_id):
            connection.execute(
                text(
                    """
                    INSERT INTO graph_nodes (
                        id, project_id, type, position_x, position_y, data
                    ) VALUES (
                        :id, :project_id, 'prompt', 0, 0, CAST('{}' AS jsonb)
                    )
                    """
                ),
                {"id": node_id, "project_id": project_id},
            )
        connection.execute(
            text(
                """
                INSERT INTO graph_edges (
                    id, project_id, source_node_id, target_node_id
                ) VALUES (:id, :project_id, :source, :target)
                """
            ),
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source": source_id,
                "target": target_id,
            },
        )

    migrate(postgres_engine)

    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM projects WHERE id = :id"),
                {"id": project_id},
            )
            == 1
        )
        assert connection.scalar(text("SELECT count(*) FROM graph_nodes")) == 0
        assert connection.scalar(text("SELECT count(*) FROM graph_edges")) == 0


def test_subject_migration_renames_data_and_restores_version_trigger(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine, "b7a4f0c9d2e1")
    old_prompt = "historical prompt must remain byte-for-byte"
    old_params = {"fixture": "unchanged", "seed": 42}
    with postgres_engine.begin() as connection:
        project_id = insert_project(connection)
        source_id = insert_node(connection, project_id)
        target_id = insert_node(connection, project_id)
        frozen_request = {
            "node_id": str(target_id),
            "op": "edit_inpaint",
            "prompt_at_runtime": old_prompt,
            "seed": 42,
            "settings": {"aspect_ratio": "1:1", "width": 1024, "height": 1024},
            "base": None,
            "connects": [],
            "mask": None,
            "input_snapshot": {
                "base_version_id": None,
                "connect_version_ids": [],
                "mask_hash": None,
            },
            "edit_depth": 0,
        }
        version_id = insert_version(
            connection,
            project_id,
            source_id,
            input_snapshot={
                "base_version_id": None,
                "connect_version_ids": [],
                "mask_hash": None,
            },
            frozen_request=frozen_request,
            params=old_params,
            prompt_at_runtime=old_prompt,
        )
        connection.execute(
            text(
                """
                INSERT INTO graph_edges (
                    id, project_id, source_node_id, target_node_id,
                    role, pin_mode, pinned_version_id
                ) VALUES (
                    :id, :project_id, :source, :target,
                    'base', 'version', :version
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source": source_id,
                "target": target_id,
                "version": version_id,
            },
        )
        connection.execute(
            text(
                "UPDATE graph_nodes SET mask_rle = 'rle', mask_width = 1, "
                "mask_height = 1, mask_base_version_id = :version WHERE id = :target"
            ),
            {"version": version_id, "target": target_id},
        )

    migrate(postgres_engine)

    with postgres_engine.connect() as connection:
        edge_role = connection.scalar(
            text("SELECT role FROM graph_edges WHERE target_node_id = :target"),
            {"target": target_id},
        )
        migrated_version = (
            connection.execute(
                text(
                    "SELECT input_snapshot, params, prompt_at_runtime "
                    "FROM versions WHERE id = :id"
                ),
                {"id": version_id},
            )
            .mappings()
            .one()
        )
        migrated_job = connection.scalar(
            text("SELECT frozen_request FROM run_jobs WHERE node_id = :node"),
            {"node": source_id},
        )
        assert edge_role == "subject"
        assert (
            connection.scalar(
                text(
                    "SELECT mask_subject_version_id FROM graph_nodes WHERE id = :target"
                ),
                {"target": target_id},
            )
            == version_id
        )
        assert migrated_version["input_snapshot"] == {
            "subject_version_id": None,
            "connect_version_ids": [],
            "mask_hash": None,
        }
        assert migrated_version["params"] == old_params
        assert migrated_version["prompt_at_runtime"] == old_prompt
        assert migrated_job["subject"] is None
        assert "base" not in migrated_job
        assert migrated_job["input_snapshot"]["subject_version_id"] is None
        assert "base_version_id" not in migrated_job["input_snapshot"]
        assert (
            connection.scalar(
                text("SELECT count(*) FROM graph_edges WHERE role = 'base'")
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM pg_constraint constraint_row
                    WHERE constraint_row.conrelid = 'graph_edges'::regclass
                      AND pg_get_constraintdef(constraint_row.oid) LIKE '%base%'
                    """
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    """
                SELECT count(*)
                FROM pg_index index_row
                WHERE index_row.indrelid = 'graph_edges'::regclass
                  AND coalesce(
                      pg_get_expr(index_row.indpred, index_row.indrelid), ''
                  ) LIKE '%base%'
                """
                )
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    """
                SELECT tgenabled
                FROM pg_trigger
                WHERE tgrelid = 'versions'::regclass
                  AND tgname = 'versions_insert_only'
                """
                )
            )
            == "O"
        )

    for statement in (
        "UPDATE versions SET prompt_at_runtime = 'changed' WHERE id = :id",
        "DELETE FROM versions WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="versions are insert-only"):
            with postgres_engine.begin() as connection:
                connection.execute(text(statement), {"id": version_id})


def test_version_trigger_rejects_updates_and_deletes(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine)
    with postgres_engine.begin() as connection:
        project_id = insert_project(connection)
        node_id = insert_node(connection, project_id)
        version_id = insert_version(connection, project_id, node_id)

    for statement in (
        "UPDATE versions SET artifact_url = 'https://changed.test' WHERE id = :id",
        "DELETE FROM versions WHERE id = :id",
    ):
        with pytest.raises(DBAPIError, match="versions are insert-only"):
            with postgres_engine.begin() as connection:
                connection.execute(text(statement), {"id": version_id})


def test_role_pin_constraint_rejects_invalid_pair(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine)
    with postgres_engine.begin() as connection:
        project_id = insert_project(connection)
        source_id = insert_node(connection, project_id)
        target_id = insert_node(connection, project_id)

    with pytest.raises(DBAPIError, match="ck_graph_edges_role_pin"):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO graph_edges (
                        id, project_id, source_node_id, target_node_id,
                        role, pin_mode
                    ) VALUES (
                        :id, :project_id, :source, :target, 'subject', 'active'
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "source": source_id,
                    "target": target_id,
                },
            )


def test_partial_unique_index_rejects_second_subject(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine)
    with postgres_engine.begin() as connection:
        project_id = insert_project(connection)
        first_source = insert_node(connection, project_id)
        second_source = insert_node(connection, project_id)
        target_id = insert_node(connection, project_id)
        first_version = insert_version(connection, project_id, first_source)
        second_version = insert_version(connection, project_id, second_source)
        connection.execute(
            text(
                """
                INSERT INTO graph_edges (
                    id, project_id, source_node_id, target_node_id, role,
                    pin_mode, pinned_version_id
                ) VALUES (
                    :id, :project_id, :source, :target,
                    'subject', 'version', :version
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source": first_source,
                "target": target_id,
                "version": first_version,
            },
        )

    with pytest.raises(DBAPIError, match="uq_graph_edges_one_subject_per_target"):
        with postgres_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO graph_edges (
                        id, project_id, source_node_id, target_node_id, role,
                        pin_mode, pinned_version_id
                    ) VALUES (
                        :id, :project_id, :source, :target,
                        'subject', 'version', :version
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "source": second_source,
                    "target": target_id,
                    "version": second_version,
                },
            )


def test_connect_cap_holds_under_concurrent_inserts(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine)
    with postgres_engine.begin() as connection:
        project_id = insert_project(connection)
        sources = [insert_node(connection, project_id) for _ in range(3)]
        target_id = insert_node(connection, project_id)
        connection.execute(
            text(
                """
                INSERT INTO graph_edges (
                    id, project_id, source_node_id, target_node_id, role,
                    pin_mode, connect_order
                ) VALUES (
                    :id, :project_id, :source, :target, 'connect', 'active', 0
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "project_id": project_id,
                "source": sources[0],
                "target": target_id,
            },
        )

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def insert_connect(source_id: uuid.UUID, order: int) -> None:
        barrier.wait()
        try:
            with postgres_engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO graph_edges (
                            id, project_id, source_node_id, target_node_id,
                            role, pin_mode, connect_order
                        ) VALUES (
                            :id, :project_id, :source, :target,
                            'connect', 'active', :order
                        )
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "project_id": project_id,
                        "source": source_id,
                        "target": target_id,
                        "order": order,
                    },
                )
            outcome = "committed"
        except DBAPIError as error:
            outcome = str(error)
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [
        threading.Thread(target=insert_connect, args=(sources[1], 1)),
        threading.Thread(target=insert_connect, args=(sources[2], 2)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert outcomes.count("committed") == 1
    assert sum("at most two connect edges" in outcome for outcome in outcomes) == 1
    with postgres_engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM graph_edges "
                    "WHERE target_node_id = :target AND role = 'connect'"
                ),
                {"target": target_id},
            )
            == 2
        )


def test_navy_shoe_path_runs_end_to_end_on_postgres_with_fake_provider(
    postgres_engine: Engine,
) -> None:
    migrate(postgres_engine)
    postgres_sessions = sessionmaker(
        bind=postgres_engine, autoflush=False, autocommit=False
    )
    enqueuer = CapturingEnqueuer()
    provider = FakeProvider()

    def override_get_db() -> Generator[Session, None, None]:
        with postgres_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_run_enqueuer] = lambda: enqueuer
    try:
        with TestClient(app) as client:
            project = client.post("/api/projects", json={"name": "Shoe"}).json()
            shoe = client.post(
                f"/api/projects/{project['id']}/nodes",
                json={
                    "prompt": "A blue running shoe",
                    "position": {"x": 100, "y": 100},
                },
            ).json()
            generate = client.post(
                f"/api/projects/{project['id']}/nodes/{shoe['id']}/runs",
                json={"idempotency_key": "postgres-shoe-generate"},
            )
            assert generate.status_code == 202
            subject_version_id = execute_run_job(
                job_id=enqueuer.job_ids[-1],
                session_factory=postgres_sessions,
                provider=provider,
                ingestor=FakeIngestor(),
            )

            branch = client.post(
                f"/api/projects/{project['id']}/nodes",
                json={
                    "prompt": "make it navy",
                    "position": {"x": 500, "y": 100},
                },
            ).json()
            wire = client.put(
                f"/api/projects/{project['id']}/nodes/{branch['id']}/subject",
                json={
                    "source_node_id": shoe["id"],
                    "version_id": str(subject_version_id),
                },
            )
            assert wire.status_code == 200
            queued = client.post(
                f"/api/projects/{project['id']}/nodes/{branch['id']}/runs",
                json={"idempotency_key": "postgres-navy-edit"},
            )
            assert queued.status_code == 202
            navy_version_id = execute_run_job(
                job_id=enqueuer.job_ids[-1],
                session_factory=postgres_sessions,
                provider=provider,
                ingestor=FakeIngestor(),
            )
            graph = client.get(f"/api/projects/{project['id']}/graph").json()

        target = next(node for node in graph["nodes"] if node["id"] == branch["id"])
        assert target["active_version_id"] == str(navy_version_id)
        assert target["versions"][0]["op"] == "edit_instruct"
        assert target["versions"][0]["artifact_url"].endswith("same-shoe-navy.png")
        assert provider.requests[-1].subject is not None
        assert provider.requests[-1].subject.id == str(subject_version_id)
    finally:
        app.dependency_overrides.clear()
