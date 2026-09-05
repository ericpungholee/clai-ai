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
  whiteBackground: boolean;
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
    subject_version_id: string | null;
    connect_version_ids: string[];
    mask_hash: string | null;
  };
  prompt_at_runtime: string;
  edit_depth: number;
  hidden: boolean;
  branch_node_ids: string[];
  masked_outside_change: number | null;
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
  mask: MaskData | null;
  document: PromptPart[];
  revision: number;
  deleted: boolean;
};

export type PromptPart =
  | { type: "text"; text: string }
  | { type: "connect"; edge_id: string; source_node_id: string };
export type ConnectPreview = {
  edgeId: string;
  nodeId: string;
  title: string;
  state: "ready" | "empty" | "deleted";
};

export type MaskData = {
  rle: string;
  width: number;
  height: number;
  subject_version_id: string;
};

export type VersionPin = { mode: "version"; version_id: string };
export type ActivePin = { mode: "active" };

export type PersistedGraphEdge = {
  id: string;
  source_node_id: string;
  target_node_id: string;
} & (
  | { role: "subject"; pin: VersionPin; order: null }
  | { role: "connect"; pin: ActivePin; order: number }
);

export type GraphDocument = {
  nodes: PersistedGraphNode[];
  edges: PersistedGraphEdge[];
};

export type SubjectPreview = {
  nodeId: string;
  deleted: boolean;
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
  subject: SubjectPreview | null;
  mask: MaskData | null;
  document: PromptPart[];
  revision: number;
  connects: ConnectPreview[];
  resolvedOp: Op;
  runState: "idle" | "running" | "failed";
  runError: string | null;
  meshPreview: { versionId: string; url: string } | null;
} & Record<string, unknown>;

export type WorkspaceEdgeData = (
  { role: "subject"; pin: VersionPin } | { role: "connect"; pin: ActivePin }
) &
  Record<string, unknown>;

export type WorkspaceNode = Node<DesignNodeData, "design">;
export type WorkspaceEdge = Edge<WorkspaceEdgeData>;

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

export async function saveMask(
  projectId: string,
  nodeId: string,
  mask: MaskData | null,
): Promise<MaskData | null> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/mask`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(mask),
    },
  );
}

export async function selectMask(
  projectId: string,
  versionId: string,
  text: string,
  points: { x: number; y: number; label: 0 | 1 }[],
): Promise<MaskData | null> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/selection`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, points }),
    },
  );
}

export async function getGraph(projectId: string): Promise<GraphDocument> {
  return apiRequest<GraphDocument>(
    `${typeof window === "undefined" ? serverApiUrl : browserApiUrl}/api/projects/${projectId}/graph`,
    { cache: "no-store" },
  );
}

export async function savePrompt(
  projectId: string,
  nodeId: string,
  document: PromptPart[],
  revision: number,
): Promise<GraphDocument> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/prompt`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document, expected_revision: revision }),
    },
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

export async function replaceSubjectEdge(
  projectId: string,
  targetNodeId: string,
  input: { source_node_id: string; version_id: string },
): Promise<PersistedGraphEdge> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${targetNodeId}/subject`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export async function deleteSubjectEdge(
  projectId: string,
  targetNodeId: string,
): Promise<void> {
  await apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${targetNodeId}/subject`,
    { method: "DELETE" },
  );
}

export async function createBranch(
  projectId: string,
  versionId: string,
  input: {
    id: string;
    position: { x: number; y: number };
    prompt?: string;
    title?: string;
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

export type CollapsePreview =
  | {
      status: "ready";
      root_version_id: string;
      instruction: string;
      steps: number;
    }
  | { status: "unavailable"; reason: string };

export async function getCollapsePreview(
  projectId: string,
  versionId: string,
): Promise<CollapsePreview> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/collapse-preview`,
    { cache: "no-store" },
  );
}

export async function setVersionHidden(
  projectId: string,
  versionId: string,
  hidden: boolean,
): Promise<void> {
  await apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/visibility`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hidden }),
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
  const subjectByTarget = new Map(
    graph.edges
      .filter(
        (edge): edge is PersistedGraphEdge & { pin: VersionPin } =>
          edge.role === "subject" && edge.pin.mode === "version",
      )
      .map((edge) => [edge.target_node_id, edge]),
  );

  return {
    nodes: graph.nodes
      .filter((node) => !node.deleted)
      .map((node) => {
        const edge = subjectByTarget.get(node.id);
        const source = edge ? nodesById.get(edge.source_node_id) : undefined;
        const pinned =
          edge && source
            ? source.versions.find(
                (version) => version.id === edge.pin.version_id,
              )
            : undefined;
        const subject =
          edge && source && pinned
            ? {
                nodeId: source.id,
                deleted: source.deleted,
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
            meshPreview: null,
            subject,
            mask: node.mask,
            document: node.document,
            revision: node.revision,
            connects: node.document.flatMap((part): ConnectPreview[] => {
              if (part.type === "text") return [];
              const source = nodesById.get(part.source_node_id);
              return [
                {
                  edgeId: part.edge_id,
                  nodeId: part.source_node_id,
                  title: source?.title ?? "Deleted concept",
                  state:
                    !source || source.deleted
                      ? "deleted"
                      : source.active_version_id
                        ? "ready"
                        : "empty",
                },
              ];
            }),
            resolvedOp: resolveOp({
              hasSubject: subject !== null,
              hasMask: subject !== null && node.mask !== null,
              connectCount: node.document.filter(
                (part) => part.type === "connect",
              ).length,
            }),
            runState: "idle" as const,
            runError: null,
          },
        };
      }),
    edges: graph.edges
      .filter(
        (edge) =>
          !nodesById.get(edge.source_node_id)?.deleted &&
          !nodesById.get(edge.target_node_id)?.deleted,
      )
      .map(toWorkspaceEdge),
  };
}

export function toWorkspaceEdge(edge: PersistedGraphEdge): WorkspaceEdge {
  return {
    id: edge.id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    sourceHandle: "source",
    targetHandle: edge.role,
    style:
      edge.role === "subject"
        ? { stroke: "#0284c7", strokeWidth: 2 }
        : { stroke: "#a855f7", strokeWidth: 2, strokeDasharray: "5 4" },
    data:
      edge.role === "subject"
        ? { role: "subject", pin: edge.pin }
        : { role: "connect", pin: edge.pin },
  };
}

export function resolveOp(input: {
  hasSubject: boolean;
  hasMask: boolean;
  connectCount: number;
}): Op {
  if (input.connectCount < 0 || input.connectCount > 2) {
    throw new Error("A run accepts between zero and two connects");
  }
  if (input.hasMask && !input.hasSubject) {
    throw new Error("A mask requires a subject");
  }
  if (!input.hasSubject && input.connectCount === 0) return "generate";
  if (!input.hasSubject) return "generate_ref";
  if (input.hasMask && input.connectCount === 0) return "edit_inpaint";
  if (input.hasMask) return "edit_composite";
  if (input.connectCount > 0) return "edit_ref_guided";
  return "edit_instruct";
}

async function apiRequest<T>(input: string, init?: RequestInit): Promise<T> {
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
