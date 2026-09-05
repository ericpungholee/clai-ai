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
  run_signature?: string | null;
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
  run: RunJob | null;
};

export type PromptPart =
  | { type: "text"; text: string }
  | { type: "connect"; edge_id: string; source_node_id: string };
export type RunPreview = { op: Op; run_signature: string };

export type ConnectPreview = {
  versionId: string | null;
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
  edgeId: string;
  nodeId: string;
  deleted: boolean;
  nodeTitle: string;
  versionId: string;
  artifactUrl: string;
};

export type NodeRunState =
  | { status: "idle" }
  | { status: "running"; job: RunJob | null; startedAt: string }
  | { status: "failed"; message: string };

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
  remoteDeleted: boolean;
  run: NodeRunState;
  draftError: string | null;
  meshPreview: { versionId: string; url: string } | null;
  previewMode: "image" | "mesh";
  runPreview: { key: string; signature: string } | null;
  wireHighlighted?: boolean;
  saveState: "saved" | "saving" | "failed";
  highlightedWireId: string | null;
} & Record<string, unknown>;

export type WorkspaceEdgeData = (
  { role: "subject"; pin: VersionPin } | { role: "connect"; pin: ActivePin }
) & {
  number: number;
  state: "ready" | "empty" | "deleted";
  highlighted?: boolean;
  dimmed?: boolean;
} & Record<string, unknown>;

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

export async function duplicateDesignNode(
  projectId: string,
  nodeId: string,
  position: { x: number; y: number },
): Promise<PersistedGraphNode> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/duplicate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: crypto.randomUUID(), position }),
    },
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
  reroll = false,
): Promise<RunJob> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/runs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        idempotency_key: idempotencyKey,
        ...(reroll ? { reroll: true } : {}),
      }),
    },
  );
}

export async function getRunPreview(
  projectId: string,
  nodeId: string,
): Promise<RunPreview> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/nodes/${nodeId}/run-preview`,
    { cache: "no-store" },
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

  const workspace: { nodes: WorkspaceNode[]; edges: WorkspaceEdge[] } = {
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
                edgeId: edge.id,
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
            previewMode: "image",
            runPreview: null,
            saveState: "saved",
            highlightedWireId: null,
            subject,
            mask: node.mask,
            document: node.document,
            revision: node.revision,
            connects: node.document.flatMap((part): ConnectPreview[] => {
              if (part.type === "text") return [];
              const source = nodesById.get(part.source_node_id);
              return [
                {
                  versionId: source?.active_version_id ?? null,
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
            remoteDeleted: false,
            run: runDisplay(node.run),
            draftError: null,
          },
        };
      }),
    edges: graph.edges
      .filter(
        (edge) =>
          edge.role === "subject" &&
          !nodesById.get(edge.target_node_id)?.deleted,
      )
      .map((edge) => ({
        id: edge.id,
        type: "role",
        source: edge.source_node_id,
        target: edge.target_node_id,
        sourceHandle: "subject",
        targetHandle: "subject",
        data: {
          role: "subject" as const,
          pin: edge.pin as VersionPin,
          number: 1,
          state: "ready" as const,
        },
      })),
  };
  return {
    nodes: workspace.nodes,
    edges: workspaceWires(workspace.nodes, workspace.edges),
  };
}

export function runDisplay(job: RunJob | null): NodeRunState {
  if (!job || job.status === "complete") return { status: "idle" };
  if (job.status === "failed")
    return {
      status: "failed",
      message: job.error ?? "The provider could not finish this run.",
    };
  return { status: "running", job, startedAt: job.created_at };
}

// Numbering follows compile_document: origin references start at 1; a subject
// occupies image 1 on edit nodes. Derive wires from the same draft as the chips.
export function referenceNumber(index: number, hasSubject: boolean): number {
  return index + (hasSubject ? 2 : 1);
}

export function workspaceWires(
  nodes: WorkspaceNode[],
  edges: WorkspaceEdge[],
): WorkspaceEdge[] {
  const ids = new Set(nodes.map((node) => node.id));
  return [
    ...edges.filter(
      (edge) =>
        edge.data?.role === "subject" &&
        ids.has(edge.source) &&
        ids.has(edge.target),
    ),
    ...nodes.flatMap((target) =>
      target.data.connects.map((ref, index): WorkspaceEdge => ({
        id: ref.edgeId,
        type: "role",
        source: ids.has(ref.nodeId) ? ref.nodeId : target.id,
        target: target.id,
        sourceHandle: "connect",
        targetHandle: "connect",
        selected: edges.find((edge) => edge.id === ref.edgeId)?.selected,
        data: {
          role: "connect",
          pin: { mode: "active" },
          number: referenceNumber(index, !!target.data.subject),
          state: ref.state,
        },
      })),
    ),
  ].map((edge) => ({
    ...edge,
    ariaLabel: `${edge.data?.role === "subject" ? "Subject" : "Reference"} image ${edge.data?.number}`,
    interactionWidth: 24,
    zIndex: 5,
  }));
}

// This is only a cache/invalidation key. Input equivalence is decided by the
// backend signature, never by reconstructing the compiled prompt in the client.
export function runInputKey(data: DesignNodeData): string {
  return JSON.stringify([
    data.document,
    data.settings,
    data.seed,
    data.subject?.versionId ?? null,
    data.connects.map((ref) => [ref.nodeId, ref.versionId, ref.state]),
    data.mask,
  ]);
}

export function settledRunReason(data: DesignNodeData): string | null {
  const index = data.versions.findIndex(
    (version) => version.id === data.activeVersionId,
  );
  const signature = data.versions[index]?.run_signature;
  if (
    data.run.status === "running" ||
    !signature ||
    data.runPreview?.signature !== signature ||
    data.runPreview.key !== runInputKey(data)
  )
    return null;
  return `No changes since v${index + 1}. Edit the prompt or change an input.`;
}

export function nodeIsBlocked(data: DesignNodeData): boolean {
  const reason = runBlockingReason(data);
  return (
    !!reason && reason !== "Enter a prompt." && reason !== "Run in progress."
  );
}

export function runBlockingReason(data: DesignNodeData): string | null {
  if (data.remoteDeleted) return "Node deleted — copy the draft to a new node.";
  if (data.connects.some((ref) => ref.state === "deleted"))
    return "Source node deleted — remove the reference.";
  if (data.connects.some((ref) => ref.state === "empty"))
    return "Reference has no image — run its source.";
  if (
    data.mask &&
    data.mask.rle !== `1 ${data.mask.width * data.mask.height}` &&
    data.connects.length > 0
  )
    return "Area selection blocks references — clear it.";
  if (data.mask && data.mask.subject_version_id !== data.subject?.versionId)
    return "Different subject version — select the area again.";
  if (!data.prompt.trim()) return "Enter a prompt.";
  if (data.run.status === "running") return "Run in progress.";
  return null;
}

async function apiRequest<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const value =
      body && typeof body === "object" && "detail" in body ? body.detail : null;
    const detail =
      typeof value === "string"
        ? value
        : Array.isArray(value)
          ? value
              .map((item: unknown) =>
                item &&
                typeof item === "object" &&
                "msg" in item &&
                typeof item.msg === "string"
                  ? item.msg
                  : "Invalid field",
              )
              .join(". ")
          : "Request failed";
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
