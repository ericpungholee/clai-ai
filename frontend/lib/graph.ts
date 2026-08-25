import type { Edge, Node } from "@xyflow/react";

export type GraphNodeType = "prompt" | "image" | "model3d";

export type GraphNodeData = {
  text?: string;
} & Record<string, unknown>;

export type WorkspaceNode = Node<GraphNodeData, GraphNodeType>;
export type WorkspaceEdge = Edge;

export type PersistedGraphNode = {
  id: string;
  type: GraphNodeType;
  position: {
    x: number;
    y: number;
  };
  data: GraphNodeData;
};

export type PersistedGraphEdge = {
  id: string;
  source: string;
  target: string;
  source_handle: string | null;
  target_handle: string | null;
};

export type GraphDocument = {
  nodes: PersistedGraphNode[];
  edges: PersistedGraphEdge[];
};

const serverApiUrl =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const browserApiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getGraph(projectId: string): Promise<GraphDocument> {
  const response = await fetch(
    `${serverApiUrl}/api/projects/${projectId}/graph`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error("Unable to load graph");
  }

  return response.json();
}

export async function saveGraph(
  projectId: string,
  graph: GraphDocument,
): Promise<void> {
  const response = await fetch(
    `${browserApiUrl}/api/projects/${projectId}/graph`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(graph),
    },
  );

  if (!response.ok) {
    throw new Error("Unable to save graph");
  }
}

export function toWorkspaceNodes(
  nodes: PersistedGraphNode[],
): WorkspaceNode[] {
  return nodes.map((node) => ({
    id: node.id,
    type: node.type,
    position: node.position,
    data: node.data,
  }));
}

export function toWorkspaceEdges(
  edges: PersistedGraphEdge[],
): WorkspaceEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.source_handle ?? undefined,
    targetHandle: edge.target_handle ?? undefined,
  }));
}

export function toGraphDocument(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
): GraphDocument {
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      source_handle: edge.sourceHandle ?? null,
      target_handle: edge.targetHandle ?? null,
    })),
  };
}
