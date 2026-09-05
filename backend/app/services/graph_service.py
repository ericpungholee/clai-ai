import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.prompts import document_text, text_document
from app.models.graph import (
    GraphEdge,
    GraphNode,
    RunJob,
    Version,
    VersionMetric,
)
from app.schemas.graph import (
    ActivePinData,
    BranchCreate,
    BranchData,
    ConnectEdgeData,
    GraphDocument,
    GraphEdgeData,
    GraphNodeData,
    GraphPosition,
    MaskData,
    NodeCreate,
    NodeSettingsData,
    NodeUpdate,
    PromptConnectData,
    PromptUpdate,
    RunJobData,
    SubjectEdgeData,
    SubjectEdgeReplace,
    VersionData,
    VersionPinData,
)


class GraphMutationError(ValueError):
    pass


class GraphConflictError(GraphMutationError):
    pass


def assert_draft_editable(node: GraphNode, db: Session) -> None:
    if db.scalar(select(Version.id).where(Version.node_id == node.id).limit(1)):
        raise GraphConflictError(
            "This node has an image and is frozen. Continue editing or "
            "Revise prompt to make a new node."
        )
    if db.scalar(
        select(RunJob.id)
        .where(
            RunJob.node_id == node.id,
            RunJob.status.in_(
                ("queued", "dispatching", "provider_pending", "ingesting")
            ),
        )
        .limit(1)
    ):
        raise GraphConflictError(
            "Run in progress. Wait for it to finish before editing."
        )


def read_graph_document(project_id: uuid.UUID, db: Session) -> GraphDocument:
    nodes = list(
        db.scalars(
            select(GraphNode)
            .where(GraphNode.project_id == project_id)
            .order_by(GraphNode.created_at, GraphNode.id)
        )
    )
    node_ids = [node.id for node in nodes]
    versions = (
        list(
            db.scalars(
                select(Version)
                .where(Version.node_id.in_(node_ids))
                .order_by(Version.created_at, Version.id)
            )
        )
        if node_ids
        else []
    )
    versions_by_node: dict[uuid.UUID, list[Version]] = {}
    for version in versions:
        versions_by_node.setdefault(version.node_id, []).append(version)

    edges = list(
        db.scalars(
            select(GraphEdge)
            .where(GraphEdge.project_id == project_id)
            .order_by(GraphEdge.created_at, GraphEdge.id)
        )
    )
    document = GraphDocument(
        nodes=[
            serialize_node(node, versions_by_node.get(node.id, [])) for node in nodes
        ],
        edges=[serialize_edge(edge) for edge in edges],
    )
    version_ids = [version.id for version in versions]
    masked_metrics = {
        metric.version_id: metric.change_magnitude
        for metric in db.scalars(
            select(VersionMetric).where(
                VersionMetric.version_id.in_(version_ids),
                VersionMetric.method == "outside_feather_pixel_diff",
                VersionMetric.status == "complete",
            )
        )
    }
    alive = {node.id for node in nodes if node.deleted_at is None}
    branches: dict[uuid.UUID, list[uuid.UUID]] = {}
    for edge in edges:
        if (
            edge.role == "subject"
            and edge.pinned_version_id
            and edge.target_node_id in alive
        ):
            branches.setdefault(edge.pinned_version_id, []).append(edge.target_node_id)
    for node in document.nodes:
        for version in node.versions:
            version.branch_node_ids = branches.get(version.id, [])
            if version.op in {"edit_inpaint", "edit_composite"}:
                version.masked_outside_change = masked_metrics.get(version.id)
    ranked = (
        select(
            RunJob.id,
            func.row_number()
            .over(
                partition_by=RunJob.node_id,
                order_by=(RunJob.created_at.desc(), RunJob.id.desc()),
            )
            .label("rank"),
        )
        .where(RunJob.project_id == project_id)
        .subquery()
    )
    jobs = db.execute(
        select(
            RunJob.id,
            RunJob.node_id,
            RunJob.status,
            RunJob.attempts,
            RunJob.error,
            RunJob.created_at,
            RunJob.completed_at,
            RunJob.frozen_request["op"].as_string().label("op"),
        )
        .join(ranked, ranked.c.id == RunJob.id)
        .where(ranked.c.rank == 1)
    )
    versions_by_job = {version.run_job_id: version.id for version in versions}
    runs = {
        row.node_id: RunJobData(**row._mapping, version_id=versions_by_job.get(row.id))
        for row in jobs
    }
    for node in document.nodes:
        node.run = runs.get(node.id)
    return document


def create_node(project_id: uuid.UUID, data: NodeCreate, db: Session) -> GraphNode:
    node = GraphNode(
        id=data.id,
        project_id=project_id,
        title=data.title,
        prompt=text_document(data.prompt),
        settings=data.settings.model_dump(),
        seed=data.seed,
        position_x=data.position.x,
        position_y=data.position.y,
    )
    db.add(node)
    db.flush()
    return node


def update_node(node: GraphNode, data: NodeUpdate, db: Session) -> GraphNode:
    if data.model_fields_set & {"prompt", "settings", "seed", "subject", "mask"}:
        assert_draft_editable(node, db)
    if data.model_fields_set & {"subject", "mask"}:
        raise GraphMutationError(
            "Use the input image or area selection endpoint to edit this field."
        )
    if data.expected_revision is not None and data.expected_revision != node.revision:
        raise GraphConflictError(
            "This node changed in another tab. Reload its latest draft before saving."
        )
    fields = data.model_fields_set
    if "title" in fields and data.title is not None:
        node.title = data.title
    if "prompt" in fields and data.prompt is not None:
        if any(part["type"] == "connect" for part in node.prompt):
            raise GraphMutationError(
                "Edit the prompt document to preserve its references"
            )
        node.prompt = text_document(data.prompt)
    if "settings" in fields and data.settings is not None:
        node.settings = data.settings.model_dump()
    if "seed" in fields:
        node.seed = data.seed
    if "position" in fields and data.position is not None:
        node.position_x = data.position.x
        node.position_y = data.position.y
    if "active_version_id" in fields:
        images = list(db.scalars(select(Version.id).where(Version.node_id == node.id)))
        if images and (
            data.active_version_id is None
            or (len(images) == 1 and data.active_version_id != images[0])
        ):
            raise GraphConflictError("A result always presents its image.")
        _validate_active_version(node, data.active_version_id, db)
        node.active_version_id = data.active_version_id
    node.updated_at = datetime.now(UTC)
    node.revision += 1
    db.flush()
    return node


def update_prompt(
    project_id: uuid.UUID, node_id: uuid.UUID, data: PromptUpdate, db: Session
) -> GraphNode:
    node = _lock_node(project_id, node_id, db)
    assert_draft_editable(node, db)
    if node.mask_rle and any(part.type == "connect" for part in data.document):
        raise GraphMutationError(
            "Area selections can't be combined with references. Remove "
            "the selection first."
        )
    if data.expected_revision != node.revision:
        raise GraphConflictError(
            "This prompt changed in another tab. Reload its latest draft before saving."
        )
    chips = [part for part in data.document if isinstance(part, PromptConnectData)]
    if len(chips) > 2:
        raise GraphMutationError("Two references maximum. Remove one first.")
    if len({part.source_node_id for part in chips}) != len(chips) or len(
        {part.edge_id for part in chips}
    ) != len(chips):
        raise GraphMutationError("Each reference source may appear only once")
    if any(part.source_node_id == node.id for part in chips):
        raise GraphMutationError("A node cannot reference itself")
    if sum(len(part.text) for part in data.document if part.type == "text") > 8000:
        raise GraphMutationError("The prompt is limited to 8000 characters")
    current = {
        edge.id: edge
        for edge in db.scalars(
            select(GraphEdge).where(
                GraphEdge.target_node_id == node_id, GraphEdge.role == "connect"
            )
        )
    }
    for chip in chips:
        source = db.scalar(
            select(GraphNode).where(
                GraphNode.id == chip.source_node_id, GraphNode.project_id == project_id
            )
        )
        existing = current.get(chip.edge_id)
        if source is None or (
            source.deleted_at is not None
            and (existing is None or existing.source_node_id != source.id)
        ):
            raise GraphMutationError(
                "Source deleted — remove or replace this reference."
            )
    # Replace wires and their text atoms together; flushing first permits reordering
    # without transient violations of the unique position/source constraints.
    db.execute(
        delete(GraphEdge).where(
            GraphEdge.target_node_id == node_id, GraphEdge.role == "connect"
        )
    )
    db.flush()
    for order, chip in enumerate(chips):
        db.add(
            GraphEdge(
                id=chip.edge_id,
                project_id=project_id,
                source_node_id=chip.source_node_id,
                target_node_id=node_id,
                role="connect",
                pin_mode="active",
                connect_order=order,
            )
        )
    node.prompt = [part.model_dump(mode="json") for part in data.document]
    node.revision += 1
    node.updated_at = datetime.now(UTC)
    db.flush()
    return node


def replace_subject_edge(
    *,
    project_id: uuid.UUID,
    target_node_id: uuid.UUID,
    data: SubjectEdgeReplace,
    db: Session,
) -> GraphEdge:
    target = _lock_node(project_id, target_node_id, db)
    assert_draft_editable(target, db)
    source = _lock_node(project_id, data.source_node_id, db)
    if target.id == source.id:
        raise GraphMutationError("A node cannot use itself as its input image")
    version = db.scalar(
        select(Version).where(
            Version.id == data.version_id,
            Version.node_id == source.id,
        )
    )
    if version is None:
        raise GraphMutationError("The selected input image does not exist")

    edge = db.scalar(
        select(GraphEdge)
        .where(
            GraphEdge.target_node_id == target.id,
            GraphEdge.role == "subject",
        )
        .with_for_update()
    )
    if edge is None:
        edge = GraphEdge(
            id=uuid.uuid4(),
            project_id=project_id,
            target_node_id=target.id,
            role="subject",
            pin_mode="version",
        )
        db.add(edge)
    edge.source_node_id = source.id
    edge.pinned_version_id = version.id
    edge.connect_order = None
    db.flush()
    return edge


def create_branch(
    *,
    project_id: uuid.UUID,
    source_version_id: uuid.UUID,
    data: BranchCreate,
    db: Session,
) -> BranchData:
    version = db.scalar(
        select(Version).where(
            Version.id == source_version_id,
        )
    )
    if version is None:
        raise GraphMutationError("The selected image does not exist")
    # A retained version stays branchable even if its original canvas node was deleted.
    source = db.scalar(
        select(GraphNode)
        .where(GraphNode.project_id == project_id, GraphNode.id == version.node_id)
        .with_for_update()
    )
    if source is None:
        raise GraphMutationError("The image does not belong to this project")
    node = create_node(
        project_id,
        NodeCreate(
            id=data.id,
            title=data.title,
            prompt=data.prompt,
            settings=data.settings,
            position=data.position,
        ),
        db,
    )
    edge = GraphEdge(
        id=uuid.uuid4(),
        project_id=project_id,
        source_node_id=source.id,
        target_node_id=node.id,
        role="subject",
        pin_mode="version",
        pinned_version_id=version.id,
        connect_order=None,
    )
    db.add(edge)
    db.flush()
    return BranchData(node=serialize_node(node, []), edge=serialize_edge(edge))


def serialize_node(node: GraphNode, versions: list[Version]) -> GraphNodeData:
    return GraphNodeData(
        id=node.id,
        title=node.title,
        prompt=document_text(node.prompt),
        document=node.prompt,
        revision=node.revision,
        deleted=node.deleted_at is not None,
        settings=_serialize_settings(node.settings),
        seed=node.seed,
        active_version_id=node.active_version_id
        or (versions[-1].id if versions else None),
        position=GraphPosition(x=node.position_x, y=node.position_y),
        versions=[serialize_version(version) for version in versions],
        mask=MaskData(
            rle=node.mask_rle,
            width=node.mask_width,
            height=node.mask_height,
            subject_version_id=node.mask_subject_version_id,
        )
        if node.mask_rle is not None
        else None,
    )


def serialize_version(version: Version) -> VersionData:
    return VersionData(
        id=version.id,
        node_id=version.node_id,
        created_at=version.created_at,
        artifact_url=version.artifact_url,
        op=version.op,
        provider=version.provider,
        model=version.model,
        endpoint=version.endpoint,
        params=version.params,
        seed=version.seed,
        input_snapshot=version.input_snapshot,
        prompt_at_runtime=version.prompt_at_runtime,
        edit_depth=version.edit_depth,
    )


def serialize_edge(edge: GraphEdge) -> GraphEdgeData:
    if edge.role == "subject":
        if edge.pinned_version_id is None:
            raise GraphMutationError("A persisted subject edge has no pinned version")
        return SubjectEdgeData(
            id=edge.id,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            pin=VersionPinData(version_id=edge.pinned_version_id),
        )
    if edge.connect_order is None:
        raise GraphMutationError("Connect edge has no position")
    return ConnectEdgeData(
        id=edge.id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        pin=ActivePinData(),
        order=edge.connect_order,
    )


def _lock_node(project_id: uuid.UUID, node_id: uuid.UUID, db: Session) -> GraphNode:
    node = db.scalar(
        select(GraphNode)
        .where(
            GraphNode.id == node_id,
            GraphNode.project_id == project_id,
            GraphNode.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if node is None:
        raise GraphMutationError("Node not found")
    return node


def _validate_active_version(
    node: GraphNode, version_id: uuid.UUID | None, db: Session
) -> None:
    if version_id is None:
        return
    version = db.scalar(
        select(Version.id).where(
            Version.id == version_id,
            Version.node_id == node.id,
        )
    )
    if version is None:
        raise GraphMutationError("Active version must belong to the node")


def _serialize_settings(settings: dict[str, object]) -> NodeSettingsData:
    payload = dict(settings)
    payload.setdefault("whiteBackground", False)
    return NodeSettingsData.model_validate(payload)
