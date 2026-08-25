import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.graph import GraphEdge, GraphNode
from app.models.project import Project
from app.schemas.graph import (
    GraphDocument,
    GraphEdgeData,
    GraphNodeData,
    GraphPosition,
)

router = APIRouter(prefix="/api/projects", tags=["graph"])


def get_project_or_404(project_id: uuid.UUID, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


def read_graph_document(project_id: uuid.UUID, db: Session) -> GraphDocument:
    nodes = db.scalars(
        select(GraphNode)
        .where(GraphNode.project_id == project_id)
        .order_by(GraphNode.created_at, GraphNode.id)
    )
    edges = db.scalars(
        select(GraphEdge)
        .where(GraphEdge.project_id == project_id)
        .order_by(GraphEdge.created_at, GraphEdge.id)
    )

    return GraphDocument(
        nodes=[
            GraphNodeData(
                id=node.id,
                type=node.type,
                position=GraphPosition(x=node.position_x, y=node.position_y),
                data=node.data,
            )
            for node in nodes
        ],
        edges=[
            GraphEdgeData(
                id=edge.id,
                source=edge.source_node_id,
                target=edge.target_node_id,
                source_handle=edge.source_handle,
                target_handle=edge.target_handle,
            )
            for edge in edges
        ],
    )


def reject_cross_project_ids(
    project_id: uuid.UUID,
    graph: GraphDocument,
    db: Session,
) -> None:
    node_ids = [node.id for node in graph.nodes]
    edge_ids = [edge.id for edge in graph.edges]

    foreign_node_id = (
        db.scalar(
            select(GraphNode.id)
            .where(
                GraphNode.id.in_(node_ids),
                GraphNode.project_id != project_id,
            )
            .limit(1)
        )
        if node_ids
        else None
    )
    foreign_edge_id = (
        db.scalar(
            select(GraphEdge.id)
            .where(
                GraphEdge.id.in_(edge_ids),
                GraphEdge.project_id != project_id,
            )
            .limit(1)
        )
        if edge_ids
        else None
    )

    if foreign_node_id is not None or foreign_edge_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Graph contains resources owned by another project",
        )


@router.get("/{project_id}/graph", response_model=GraphDocument)
def get_graph(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> GraphDocument:
    get_project_or_404(project_id, db)
    return read_graph_document(project_id, db)


@router.put("/{project_id}/graph", response_model=GraphDocument)
def put_graph(
    project_id: uuid.UUID,
    graph: GraphDocument,
    db: Session = Depends(get_db),
) -> GraphDocument:
    project = get_project_or_404(project_id, db)
    reject_cross_project_ids(project_id, graph, db)

    try:
        db.execute(delete(GraphEdge).where(GraphEdge.project_id == project_id))

        existing_nodes = {
            node.id: node
            for node in db.scalars(
                select(GraphNode).where(GraphNode.project_id == project_id)
            )
        }
        submitted_node_ids = {node.id for node in graph.nodes}

        for node_id, node in existing_nodes.items():
            if node_id not in submitted_node_ids:
                db.delete(node)

        for node_data in graph.nodes:
            node = existing_nodes.get(node_data.id)
            if node is None:
                node = GraphNode(id=node_data.id, project_id=project_id)
                db.add(node)

            node.type = node_data.type.value
            node.position_x = node_data.position.x
            node.position_y = node_data.position.y
            node.data = dict(node_data.data)

        db.flush()

        db.add_all(
            [
                GraphEdge(
                    id=edge.id,
                    project_id=project_id,
                    source_node_id=edge.source,
                    target_node_id=edge.target,
                    source_handle=edge.source_handle,
                    target_handle=edge.target_handle,
                )
                for edge in graph.edges
            ]
        )
        project.updated_at = datetime.now(UTC)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Graph violates database constraints",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save graph",
        ) from exc

    return read_graph_document(project_id, db)
