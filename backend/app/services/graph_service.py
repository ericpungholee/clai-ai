import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.prompts import document_text, text_document
from app.models.graph import GraphEdge, GraphNode, Version
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
    SubjectEdgeData,
    SubjectEdgeReplace,
    VersionData,
    VersionPinData,
)


class GraphMutationError(ValueError):
    pass


class GraphConflictError(GraphMutationError):
    pass


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
    return GraphDocument(
        nodes=[
            serialize_node(node, versions_by_node.get(node.id, [])) for node in nodes
        ],
        edges=[serialize_edge(edge) for edge in edges],
    )


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
                "Edit the prompt document to preserve its connect chips"
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
    if data.expected_revision != node.revision:
        raise GraphConflictError(
            "This prompt changed in another tab. Reload its latest draft before saving."
        )
    chips = [part for part in data.document if isinstance(part, PromptConnectData)]
    if len(chips) > 2:
        raise GraphMutationError("A node accepts at most two connect chips")
    if len({part.source_node_id for part in chips}) != len(chips) or len(
        {part.edge_id for part in chips}
    ) != len(chips):
        raise GraphMutationError("Each connect source may appear only once")
    if any(part.source_node_id == node.id for part in chips):
        raise GraphMutationError("A node cannot connect to itself")
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
            raise GraphMutationError("The connect source no longer exists")
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
    source = _lock_node(project_id, data.source_node_id, db)
    if target.id == source.id:
        raise GraphMutationError("A node cannot use itself as its subject")
    version = db.scalar(
        select(Version).where(
            Version.id == data.version_id,
            Version.node_id == source.id,
        )
    )
    if version is None:
        raise GraphMutationError("The selected subject version does not exist")

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
        raise GraphMutationError("The selected branch version does not exist")
    source = _lock_node(project_id, version.node_id, db)
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
        active_version_id=node.active_version_id,
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
