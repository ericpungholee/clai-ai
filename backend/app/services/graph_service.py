import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.graph import GraphEdge, GraphNode, Version
from app.schemas.graph import (
    ActivePinData,
    BranchCreate,
    BranchData,
    GraphDocument,
    GraphEdgeData,
    GraphNodeData,
    GraphPosition,
    NodeCreate,
    NodeSettingsData,
    NodeUpdate,
    SubjectEdgeReplace,
    VersionData,
    VersionPinData,
)


class GraphMutationError(ValueError):
    pass


def read_graph_document(project_id: uuid.UUID, db: Session) -> GraphDocument:
    nodes = list(
        db.scalars(
            select(GraphNode)
            .where(GraphNode.project_id == project_id, GraphNode.deleted_at.is_(None))
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
        prompt=data.prompt,
        settings=data.settings.model_dump(),
        seed=data.seed,
        position_x=data.position.x,
        position_y=data.position.y,
    )
    db.add(node)
    db.flush()
    return node


def update_node(node: GraphNode, data: NodeUpdate, db: Session) -> GraphNode:
    fields = data.model_fields_set
    if "title" in fields and data.title is not None:
        node.title = data.title
    if "prompt" in fields and data.prompt is not None:
        node.prompt = data.prompt
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
        prompt=node.prompt,
        settings=_serialize_settings(node.settings),
        seed=node.seed,
        active_version_id=node.active_version_id,
        position=GraphPosition(x=node.position_x, y=node.position_y),
        versions=[serialize_version(version) for version in versions],
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
        pin = VersionPinData(version_id=edge.pinned_version_id)
    else:
        pin = ActivePinData()
    return GraphEdgeData(
        id=edge.id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        role=edge.role,
        pin=pin,
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
