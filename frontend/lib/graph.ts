import type { Edge, Node } from "@xyflow/react";

export type Op =
  | "generate"
  | "generate_ref"
  | "edit_instruct"
  | "edit_inpaint"
  | "edit_composite"
  | "edit_ref_guided";

export type NodeSettings = {
  aspect_ratio: string;
  width: number;
  height: number;
};

export type Version = {
  id: string;
  node_id: string;
  created_at: string;
  artifact_url: string;
  op: Op;
  provider: string;
  model: string;
  endpoint: string;
  params: Record<string, unknown>;
  seed: number;
  input_snapshot: {
    base_version_id: string | null;
    connect_version_ids: string[];
    mask_hash: string | null;
  };
  prompt_at_runtime: string;
  edit_depth: number;
};

export type PersistedGraphNode = {
  id: string;
  title: string;
  prompt: string;
  settings: NodeSettings;
  seed: number | null;
  active_version_id: string | null;
  position: { x: number; y: number };
  versions: Version[];
};

export type VersionPin = { mode: "version"; version_id: string };
export type ActivePin = { mode: "active" };

export type PersistedGraphEdge = {
  id: string;
  source_node_id: string;
  target_node_id: string;
  role: "base" | "connect";
  pin: VersionPin | ActivePin;
  order: number | null;
};

export type GraphDocument = {
  nodes: PersistedGraphNode[];
  edges: PersistedGraphEdge[];
};

export type BasePreview = {
  nodeTitle: string;
  versionId: string;
  artifactUrl: string;
};

export type DesignNodeData = {
  title: string;
  prompt: string;
  settings: NodeSettings;
  seed: number | null;
  activeVersionId: string | null;
  versions: Version[];
  base: BasePreview | null;
  resolvedOp: Op;
  runState: "idle" | "running" | "failed";
  runError: string | null;
} & Record<string, unknown>;

export type BaseEdgeData = {
  role: "base";
  pin: VersionPin;
} & Record<string, unknown>;

export type WorkspaceNode = Node<DesignNodeData, "design">;
export type WorkspaceEdge = Edge<BaseEdgeData>;

export type RunJob = {
  id: string;
  node_id: string;
  status:
    | "queued"
    | "dispatching"
    | "provider_pending"
    | "ingesting"
    | "complete"
    | "failed";
  op: Op;
  attempts: number;
  error: string | null;
  version_id: string | null;
  created_at: string;
  completed_at: string | null;
};

const serverApiUrl =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const browserApiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getGraph(projectId: string): Promise<GraphDocument> {
  return apiRequest<GraphDocument>(
    `${serverApiUrl}/api/projects/${projectId}/graph`,
    { cache: "no-store" },
  );
}

export async function createDesignNode(
  projectId: string,
  input: {
    id: string;
    position: { x: number; y: number };
  },
): Promise<PersistedGraphNode> {
  return apiRequest(`${browserApiUrl}/api/projects/${projectId}/nodes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export async function patchDesignNode(
  projectId: string,
  nodeId: string,
  patch: Record<string, unknown>,
): Promise<PersistedGraphNode> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );
}

export async function deleteDesignNode(
  projectId: string,
  nodeId: string,
): Promise<void> {
  await apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}`,
    { method: "DELETE" },
  );
}

export async function replaceBaseEdge(
  projectId: string,
  targetNodeId: string,
  input: { source_node_id: string; version_id: string },
): Promise<PersistedGraphEdge> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${targetNodeId}/base`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function deleteBaseEdge(
  projectId: string,
  targetNodeId: string,
): Promise<void> {
  await apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${targetNodeId}/base`,
    { method: "DELETE" },
  );
}

export async function createBranch(
  projectId: string,
  versionId: string,
  input: {
    id: string;
    position: { x: number; y: number };
  },
): Promise<{ node: PersistedGraphNode; edge: PersistedGraphEdge }> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/branches`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function submitRun(
  projectId: string,
  nodeId: string,
  idempotencyKey: string,
): Promise<RunJob> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    },
  );
}

export async function getRun(
  projectId: string,
  runId: string,
): Promise<RunJob> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/runs/${runId}`,
    { cache: "no-store" },
  );
}

export function toWorkspaceGraph(graph: GraphDocument): {
  nodes: WorkspaceNode[];
  edges: WorkspaceEdge[];
} {
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const baseByTarget = new Map(
    graph.edges
      .filter(
        (edge): edge is PersistedGraphEdge & { pin: VersionPin } =>
          edge.role === "base" && edge.pin.mode === "version",
      )
      .map((edge) => [edge.target_node_id, edge]),
  );

  return {
    nodes: graph.nodes.map((node) => {
      const edge = baseByTarget.get(node.id);
      const source = edge ? nodesById.get(edge.source_node_id) : undefined;
      const pinned =
        edge && source
          ? source.versions.find(
              (version) => version.id === edge.pin.version_id,
            )
          : undefined;
      const base =
        edge && source && pinned
          ? {
              nodeTitle: source.title,
              versionId: pinned.id,
              artifactUrl: pinned.artifact_url,
            }
          : null;
      return {
        id: node.id,
        type: "design" as const,
        position: node.position,
        data: {
          title: node.title,
          prompt: node.prompt,
          settings: node.settings,
          seed: node.seed,
          activeVersionId: node.active_version_id,
          versions: node.versions,
          base,
          resolvedOp: resolveOp({
            hasBase: base !== null,
            hasMask: false,
            connectCount: 0,
          }),
          runState: "idle" as const,
          runError: null,
        },
      };
    }),
    edges: graph.edges
      .filter(
        (edge): edge is PersistedGraphEdge & { pin: VersionPin } =>
          edge.role === "base" && edge.pin.mode === "version",
      )
      .map((edge) => toWorkspaceEdge(edge)),
  };
}

export function toWorkspaceEdge(
  edge: PersistedGraphEdge & { pin: VersionPin },
): WorkspaceEdge {
  return {
    id: edge.id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    sourceHandle: "source",
    targetHandle: "base",
    data: { role: "base", pin: edge.pin },
  };
}

export function resolveOp(input: {
  hasBase: boolean;
  hasMask: boolean;
  connectCount: number;
}): Op {
  if (input.connectCount < 0 || input.connectCount > 2) {
    throw new Error("A run accepts between zero and two connects");
  }
  if (input.hasMask && !input.hasBase) {
    throw new Error("A mask requires a base");
  }
  if (!input.hasBase && input.connectCount === 0) return "generate";
  if (!input.hasBase) return "generate_ref";
  if (input.hasMask && input.connectCount === 0) return "edit_inpaint";
  if (input.hasMask) return "edit_composite";
  if (input.connectCount > 0) return "edit_ref_guided";
  return "edit_instruct";
}

async function apiRequest<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : "Request failed";
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
