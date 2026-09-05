"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  Panel,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeTypes,
  type ReactFlowInstance,
} from "@xyflow/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createBranch,
  createDesignNode,
  deleteSubjectEdge,
  deleteDesignNode,
  getGraph,
  getRun,
  patchDesignNode,
  replaceSubjectEdge,
  submitRun,
  savePrompt,
  setVersionHidden,
  type PromptPart,
  toWorkspaceGraph,
  type GraphDocument,
  type WorkspaceEdge,
  type WorkspaceNode,
  type Version,
} from "@/lib/graph";

import { AddNodeControl } from "./add-node-control";
import { DesignNode } from "./design-node";
import { MaskEditor } from "./mask-editor";
import { ImageViewer } from "./image-viewer";
import { MeshViewer } from "./mesh-viewer";
import { CollapseDialog } from "./collapse-dialog";
import { DesignNodeActionsContext } from "./design-node-actions";
import { SaveStatus, type SaveState } from "./save-status";

const nodeTypes = { design: DesignNode } satisfies NodeTypes;
const fitViewOptions = { padding: 0.2, maxZoom: 1 };
const defaultEdgeOptions = {
  style: { stroke: "#0284c7", strokeWidth: 1.75 },
};

function findAvailablePosition(
  center: { x: number; y: number },
  nodes: WorkspaceNode[],
): { x: number; y: number } {
  const origin = { x: center.x - 152, y: center.y - 160 };
  for (let radius = 0; radius < 10; radius += 1) {
    const offsets =
      radius === 0
        ? [{ column: 0, row: 0 }]
        : [
            { column: radius, row: 0 },
            { column: -radius, row: 0 },
            { column: 0, row: radius },
            { column: 0, row: -radius },
            { column: radius, row: radius },
            { column: -radius, row: radius },
          ];
    for (const offset of offsets) {
      const candidate = {
        x: origin.x + offset.column * 350,
        y: origin.y + offset.row * 430,
      };
      const overlaps = nodes.some(
        (node) =>
          Math.abs(node.position.x - candidate.x) < 320 &&
          Math.abs(node.position.y - candidate.y) < 390,
      );
      if (!overlaps) return candidate;
    }
  }
  return origin;
}

type GraphWorkspaceProps = {
  initialGraph: GraphDocument;
  projectId: string;
  projectName: string;
};

export function GraphWorkspace({
  initialGraph,
  projectId,
  projectName,
}: GraphWorkspaceProps) {
  const initialWorkspace = useMemo(
    () => toWorkspaceGraph(initialGraph),
    [initialGraph],
  );
  const [nodes, setNodes] = useState(initialWorkspace.nodes);
  const [edges, setEdges] = useState(initialWorkspace.edges);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [maskNodeId, setMaskNodeId] = useState<string | null>(null);
  const [viewedVersions, setViewedVersions] = useState<Version[]>([]);
  const [meshVersion, setMeshVersion] = useState<Version | null>(null);
  const [collapseVersionId, setCollapseVersionId] = useState<string | null>(
    null,
  );
  const flowInstanceRef =
    useRef<ReactFlowInstance<WorkspaceNode, WorkspaceEdge>>(null);
  const canvasRef = useRef<HTMLElement>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const patchTimersRef = useRef(new Map<string, number>());
  const mountedRef = useRef(true);
  const pendingPatches = useRef(new Map<string, Record<string, unknown>>());
  const pendingDocuments = useRef(new Map<string, PromptPart[]>());
  const saves = useRef(new Map<string, Promise<void>>());

  useEffect(() => {
    mountedRef.current = true;
    const timers = patchTimersRef.current;
    return () => {
      mountedRef.current = false;
      for (const timer of timers.values()) window.clearTimeout(timer);
    };
  }, []);

  const replaceWorkspace = useCallback((graph: GraphDocument) => {
    const workspace = toWorkspaceGraph(graph);
    workspace.nodes = workspace.nodes.map((node) => {
      const current = nodesRef.current.find((item) => item.id === node.id);
      if (!current) return node;
      const document = pendingDocuments.current.get(node.id);
      const patch = pendingPatches.current.get(node.id);
      return {
        ...node,
        selected: current.selected,
        data: {
          ...node.data,
          ...(document
            ? {
                document,
                prompt: current.data.prompt,
                connects: current.data.connects,
              }
            : {}),
          ...(patch?.title !== undefined ? { title: current.data.title } : {}),
          ...(patch?.settings !== undefined
            ? { settings: current.data.settings }
            : {}),
          runState: current.data.runState,
          meshPreview: current.data.meshPreview,
          runError: current.data.runError,
        },
      };
    });
    nodesRef.current = workspace.nodes;
    edgesRef.current = workspace.edges;
    setNodes(workspace.nodes);
    setEdges(workspace.edges);
  }, []);

  const refreshWorkspace = useCallback(async () => {
    const graph = await getGraph(projectId);
    if (mountedRef.current) replaceWorkspace(graph);
  }, [projectId, replaceWorkspace]);

  const persistNodePatch = useCallback(
    async (nodeId: string, patch: Record<string, unknown>) => {
      pendingPatches.current.set(nodeId, {
        ...pendingPatches.current.get(nodeId),
        ...patch,
      });
      const previous = saves.current.get(nodeId) ?? Promise.resolve();
      const save = previous
        .catch(() => undefined)
        .then(async () => {
          setSaveState("saving");
          const pending = pendingPatches.current.get(nodeId);
          const document = pendingDocuments.current.get(nodeId);
          if (!pending && !document) return;
          try {
            let revision = nodesRef.current.find((node) => node.id === nodeId)!
              .data.revision;
            if (pending && Object.keys(pending).length) {
              const result = await patchDesignNode(projectId, nodeId, {
                ...pending,
                expected_revision: revision,
              });
              revision = result.revision;
              if (pendingPatches.current.get(nodeId) === pending)
                pendingPatches.current.delete(nodeId);
            }
            if (
              pending &&
              !Object.keys(pending).length &&
              pendingPatches.current.get(nodeId) === pending
            )
              pendingPatches.current.delete(nodeId);
            if (document) {
              const graph = await savePrompt(
                projectId,
                nodeId,
                document,
                revision,
              );
              if (pendingDocuments.current.get(nodeId) === document)
                pendingDocuments.current.delete(nodeId);
              replaceWorkspace(graph);
            } else {
              const updated = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? { ...node, data: { ...node.data, revision } }
                  : node,
              );
              nodesRef.current = updated;
              setNodes(updated);
            }
            if (mountedRef.current) setSaveState("saved");
          } catch (error) {
            if (mountedRef.current) {
              setSaveState("failed");
              const message =
                error instanceof Error ? error.message : "Could not save";
              const updated = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? { ...node, data: { ...node.data, runError: message } }
                  : node,
              );
              nodesRef.current = updated;
              setNodes(updated);
            }
            throw error;
          }
        });
      saves.current.set(nodeId, save);
      return save;
    },
    [projectId, replaceWorkspace],
  );

  const scheduleNodePatch = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      pendingPatches.current.set(nodeId, {
        ...pendingPatches.current.get(nodeId),
        ...patch,
      });
      const currentTimer = patchTimersRef.current.get(nodeId);
      if (currentTimer !== undefined) window.clearTimeout(currentTimer);
      setSaveState("saving");
      const timer = window.setTimeout(() => {
        patchTimersRef.current.delete(nodeId);
        void persistNodePatch(nodeId, {}).catch(() => undefined);
      }, 500);
      patchTimersRef.current.set(nodeId, timer);
    },
    [persistNodePatch],
  );

  const updateNodeData = useCallback(
    (nodeId: string, patch: Partial<WorkspaceNode["data"]>) => {
      const next = nodesRef.current.map((node) =>
        node.id === nodeId
          ? { ...node, data: { ...node.data, ...patch } }
          : node,
      );
      nodesRef.current = next;
      setNodes(next);
    },
    [],
  );

  const updateDocument = useCallback(
    (nodeId: string, document: PromptPart[]) => {
      const current = nodesRef.current.find((node) => node.id === nodeId);
      if (!current) return;
      const connects = document.flatMap((part) => {
        if (part.type === "text") return [];
        const source = nodesRef.current.find(
          (node) => node.id === part.source_node_id,
        );
        return [
          {
            edgeId: part.edge_id,
            nodeId: part.source_node_id,
            title:
              source?.data.title ??
              current.data.connects.find((ref) => ref.edgeId === part.edge_id)
                ?.title ??
              "Deleted concept",
            state: !source
              ? ("deleted" as const)
              : source.data.activeVersionId
                ? ("ready" as const)
                : ("empty" as const),
          },
        ];
      });
      pendingDocuments.current.set(nodeId, document);
      updateNodeData(nodeId, {
        document,
        connects,
        prompt: document
          .map((part) => (part.type === "text" ? part.text : "@"))
          .join(""),
      });
      scheduleNodePatch(nodeId, {});
    },
    [scheduleNodePatch, updateNodeData],
  );

  const updatePrompt = useCallback(
    (nodeId: string, prompt: string) => {
      updateDocument(nodeId, [{ type: "text", text: prompt }]);
    },
    [updateDocument],
  );

  const updateTitle = useCallback(
    (nodeId: string, title: string) => {
      setNodes((current) => {
        const next = current.map((node) => {
          if (node.id === nodeId) {
            return { ...node, data: { ...node.data, title } };
          }
          const currentSubject = node.data.subject;
          if (currentSubject !== null && currentSubject.nodeId === nodeId) {
            return {
              ...node,
              data: {
                ...node.data,
                subject: {
                  ...currentSubject,
                  nodeTitle: title,
                  versionId: currentSubject.versionId,
                  artifactUrl: currentSubject.artifactUrl,
                },
              },
            };
          }
          return node;
        });
        nodesRef.current = next;
        return next;
      });
      if (title.trim()) scheduleNodePatch(nodeId, { title });
    },
    [scheduleNodePatch],
  );

  const updateWhiteBackground = useCallback(
    (nodeId: string, enabled: boolean) => {
      const node = nodesRef.current.find(
        (candidate) => candidate.id === nodeId,
      );
      if (!node) return;
      const settings = { ...node.data.settings, whiteBackground: enabled };
      updateNodeData(nodeId, { settings });
      scheduleNodePatch(nodeId, { settings });
    },
    [scheduleNodePatch, updateNodeData],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<WorkspaceNode>[]) => {
      const removedIds = changes
        .filter((change) => change.type === "remove")
        .map((change) => change.id);
      const settledPositions = changes.filter(
        (change) => change.type === "position" && change.dragging === false,
      );
      setNodes((current) => {
        const next = applyNodeChanges(changes, current);
        nodesRef.current = next;
        return next;
      });
      for (const change of settledPositions) {
        if (change.type === "position" && change.position) {
          void persistNodePatch(change.id, { position: change.position });
        }
      }
      for (const nodeId of removedIds) {
        void deleteDesignNode(projectId, nodeId)
          .then(refreshWorkspace)
          .catch(() => setSaveState("failed"));
      }
    },
    [persistNodePatch, projectId, refreshWorkspace],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<WorkspaceEdge>[]) => {
      const removed = changes
        .filter((change) => change.type === "remove")
        .map((change) => edgesRef.current.find((edge) => edge.id === change.id))
        .filter((edge): edge is WorkspaceEdge => edge !== undefined);
      setEdges((current) => {
        const next = applyEdgeChanges(changes, current);
        edgesRef.current = next;
        return next;
      });
      for (const edge of removed) {
        if (
          !nodesRef.current.some((node) => node.id === edge.source) ||
          !nodesRef.current.some((node) => node.id === edge.target)
        )
          continue;
        if (edge.data?.role === "connect") {
          const target = nodesRef.current.find(
            (node) => node.id === edge.target,
          );
          if (target)
            updateDocument(
              edge.target,
              target.data.document.filter(
                (part) => part.type !== "connect" || part.edge_id !== edge.id,
              ),
            );
          continue;
        }
        void deleteSubjectEdge(projectId, edge.target).catch(() =>
          setSaveState("failed"),
        );
      }
    },
    [projectId, updateDocument],
  );

  const onConnect = useCallback(
    async (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const source = nodesRef.current.find(
        (node) => node.id === connection.source,
      );
      if (connection.targetHandle === "connect") {
        const target = nodesRef.current.find(
          (node) => node.id === connection.target,
        );
        if (
          !target ||
          !source ||
          source.id === target.id ||
          target.data.connects.length >= 2 ||
          target.data.connects.some((ref) => ref.nodeId === source.id)
        )
          return;
        updateDocument(target.id, [
          ...target.data.document,
          { type: "text", text: " " },
          {
            type: "connect",
            edge_id: crypto.randomUUID(),
            source_node_id: source.id,
          },
        ]);
        await persistNodePatch(target.id, {}).catch(() => undefined);
        return;
      }
      if (
        !source?.data.activeVersionId ||
        connection.source === connection.target
      ) {
        setSaveState("failed");
        return;
      }
      setSaveState("saving");
      try {
        await replaceSubjectEdge(projectId, connection.target, {
          source_node_id: connection.source,
          version_id: source.data.activeVersionId,
        });
        await refreshWorkspace();
        if (mountedRef.current) setSaveState("saved");
      } catch {
        if (mountedRef.current) setSaveState("failed");
      }
    },
    [projectId, refreshWorkspace, updateDocument, persistNodePatch],
  );

  const addNode = useCallback(async () => {
    const canvasBounds = canvasRef.current?.getBoundingClientRect();
    const screenPosition = {
      x: canvasBounds ? canvasBounds.left + canvasBounds.width / 2 : 320,
      y: canvasBounds ? canvasBounds.top + canvasBounds.height / 2 : 240,
    };
    const flowPosition = flowInstanceRef.current?.screenToFlowPosition(
      screenPosition,
    ) ?? { x: 0, y: 0 };
    const position = findAvailablePosition(flowPosition, nodesRef.current);
    setSaveState("saving");
    try {
      await createDesignNode(projectId, {
        id: crypto.randomUUID(),
        position,
      });
      await refreshWorkspace();
      if (mountedRef.current) setSaveState("saved");
    } catch {
      if (mountedRef.current) setSaveState("failed");
    }
  }, [projectId, refreshWorkspace]);

  const selectVersion = useCallback(
    (nodeId: string, versionId: string) => {
      updateNodeData(nodeId, { activeVersionId: versionId });
      void persistNodePatch(nodeId, { active_version_id: versionId });
    },
    [persistNodePatch, updateNodeData],
  );

  const branchVersion = useCallback(
    async (nodeId: string, versionId: string) => {
      const source = nodesRef.current.find((node) => node.id === nodeId);
      if (!source) return;
      const preferred = { x: source.position.x + 380, y: source.position.y };
      const position = findAvailablePosition(preferred, nodesRef.current);
      setSaveState("saving");
      try {
        await createBranch(projectId, versionId, {
          id: crypto.randomUUID(),
          position,
        });
        await refreshWorkspace();
        if (mountedRef.current) setSaveState("saved");
      } catch {
        if (mountedRef.current) setSaveState("failed");
      }
    },
    [projectId, refreshWorkspace],
  );

  const runNode = useCallback(
    async (nodeId: string) => {
      const node = nodesRef.current.find(
        (candidate) => candidate.id === nodeId,
      );
      if (!node || !node.data.prompt.trim()) return;
      if (node.data.runState === "running") return;
      const timer = patchTimersRef.current.get(nodeId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        patchTimersRef.current.delete(nodeId);
      }
      updateNodeData(nodeId, { runState: "running", runError: null });
      try {
        await persistNodePatch(nodeId, {});
        let job = await submitRun(projectId, nodeId, crypto.randomUUID());
        while (job.status !== "complete" && job.status !== "failed") {
          await new Promise((resolve) => window.setTimeout(resolve, 750));
          job = await getRun(projectId, job.id);
        }
        if (job.status === "failed") {
          throw new Error(job.error ?? "Run failed");
        }
        updateNodeData(nodeId, { runState: "idle" });
        await refreshWorkspace();
        if (mountedRef.current) setSaveState("saved");
        return job.version_id ?? undefined;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Run failed";
        if (mountedRef.current) {
          updateNodeData(nodeId, { runState: "failed", runError: message });
          setSaveState("failed");
        }
      }
    },
    [projectId, refreshWorkspace, updateNodeData, persistNodePatch],
  );

  const actions = useMemo(
    () => ({
      updatePrompt,
      updateTitle,
      updateWhiteBackground,
      selectVersion,
      branchVersion,
      runNode,
      editMask: setMaskNodeId,
      collapseVersion: setCollapseVersionId,
      viewMesh: (id: string) =>
        setMeshVersion(
          nodesRef.current
            .flatMap((node) => node.data.versions)
            .find((version) => version.id === id) ?? null,
        ),
      viewImage: (nodeId: string) =>
        updateNodeData(nodeId, { meshPreview: null }),
      viewVersions: (ids: string[]) =>
        setViewedVersions(
          ids.flatMap((id) => {
            const version = nodesRef.current
              .flatMap((node) => node.data.versions)
              .find((version) => version.id === id);
            return version ? [version] : [];
          }),
        ),
      hideVersion: (versionId: string, hidden: boolean) => {
        void setVersionHidden(projectId, versionId, hidden)
          .then(refreshWorkspace)
          .catch(() => setSaveState("failed"));
      },
      updateDocument,
      candidates: (id: string) =>
        nodesRef.current
          .filter((node) => node.id !== id)
          .map((node) => ({ id: node.id, title: node.data.title })),
      hoverNode: (id: string | null) =>
        setNodes((current) =>
          current.map((node) => ({
            ...node,
            style: {
              ...node.style,
              outline: node.id === id ? "3px solid #a855f7" : undefined,
            },
          })),
        ),
      jumpNode: (id: string) => {
        const node = nodesRef.current.find((node) => node.id === id);
        if (node)
          void flowInstanceRef.current?.setCenter(
            node.position.x + 152,
            node.position.y + 180,
            { zoom: 1, duration: 350 },
          );
      },
    }),
    [
      branchVersion,
      runNode,
      selectVersion,
      updatePrompt,
      updateTitle,
      updateWhiteBackground,
      updateDocument,
      projectId,
      refreshWorkspace,
      updateNodeData,
    ],
  );

  return (
    <DesignNodeActionsContext.Provider value={actions}>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-white">
        {meshVersion ? (
          <MeshViewer
            key={meshVersion.id}
            projectId={projectId}
            version={meshVersion}
            onClose={() => setMeshVersion(null)}
            onPreview={(versionId, url) => {
              const node = nodesRef.current.find((node) =>
                node.data.versions.some((version) => version.id === versionId),
              );
              if (node)
                updateNodeData(node.id, { meshPreview: { versionId, url } });
            }}
          />
        ) : null}
        {viewedVersions.length > 0 ? (
          <ImageViewer
            versions={viewedVersions}
            onClose={() => setViewedVersions([])}
          />
        ) : null}
        {collapseVersionId ? (
          <CollapseDialog
            projectId={projectId}
            versionId={collapseVersionId}
            onClose={() => setCollapseVersionId(null)}
            onRun={async (rootId, instruction) => {
              const source = nodesRef.current.find((node) =>
                node.data.versions.some(
                  (version) => version.id === collapseVersionId,
                ),
              );
              const before = source?.data.versions.find(
                (version) => version.id === collapseVersionId,
              );
              if (!source || !before)
                throw new Error("The source is no longer on this canvas.");
              const branch = await createBranch(projectId, rootId, {
                id: crypto.randomUUID(),
                title: `${source.data.title.slice(0, 100)} · collapsed`,
                prompt: instruction,
                position: findAvailablePosition(
                  { x: source.position.x + 500, y: source.position.y },
                  nodesRef.current,
                ),
              });
              await refreshWorkspace();
              const resultId = await runNode(branch.node.id);
              setCollapseVersionId(null);
              const after = nodesRef.current
                .find((node) => node.id === branch.node.id)
                ?.data.versions.find((version) => version.id === resultId);
              if (after) setViewedVersions([before, after]);
            }}
          />
        ) : null}
        {(() => {
          const node = nodes.find((candidate) => candidate.id === maskNodeId);
          return node?.data.subject ? (
            <MaskEditor
              key={`${node.id}:${node.data.subject.versionId}`}
              projectId={projectId}
              nodeId={node.id}
              subject={node.data.subject}
              initialMask={node.data.mask}
              onClose={() => setMaskNodeId(null)}
              onSave={(mask) => {
                updateNodeData(node.id, { mask });
                setMaskNodeId(null);
              }}
            />
          ) : null;
        })()}
        <header className="grid h-14 shrink-0 grid-cols-[1fr_minmax(0,auto)_1fr] items-center border-b border-border px-4 sm:px-6">
          <Link
            className="w-fit text-sm font-medium text-neutral-600 hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            href="/"
          >
            ← Projects
          </Link>
          <h1 className="max-w-[45vw] truncate text-sm font-semibold text-foreground">
            {projectName}
          </h1>
          <SaveStatus state={saveState} />
        </header>
        <main
          aria-label="Project graph workspace"
          className="min-h-0 flex-1"
          ref={canvasRef}
        >
          <ReactFlow<WorkspaceNode, WorkspaceEdge>
            defaultEdgeOptions={defaultEdgeOptions}
            deleteKeyCode={["Backspace", "Delete"]}
            edges={edges}
            fitView
            fitViewOptions={fitViewOptions}
            nodeTypes={nodeTypes}
            nodes={nodes}
            onConnect={(connection) => void onConnect(connection)}
            onEdgesChange={onEdgesChange}
            onInit={(instance) => {
              flowInstanceRef.current = instance;
            }}
            onNodesChange={onNodesChange}
            onBeforeDelete={async ({ nodes: removing }) =>
              removing.length === 0 ||
              !edgesRef.current.some((edge) =>
                removing.some((node) => node.id === edge.source),
              ) ||
              window.confirm(
                "Delete these concepts? Connected prompts will keep broken chips until you replace or remove them.",
              )
            }
          >
            <Background
              color="#d4d4d8"
              gap={20}
              size={1}
              variant={BackgroundVariant.Dots}
            />
            <Panel position="top-left">
              <AddNodeControl onAdd={() => void addNode()} />
            </Panel>
            <Controls showInteractive={false} />
          </ReactFlow>
        </main>
      </div>
    </DesignNodeActionsContext.Provider>
  );
}
