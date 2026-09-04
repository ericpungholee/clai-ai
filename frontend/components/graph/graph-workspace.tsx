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
  toWorkspaceGraph,
  type GraphDocument,
  type WorkspaceEdge,
  type WorkspaceNode,
} from "@/lib/graph";

import { AddNodeControl } from "./add-node-control";
import { DesignNode } from "./design-node";
import { MaskEditor } from "./mask-editor";
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
  const flowInstanceRef =
    useRef<ReactFlowInstance<WorkspaceNode, WorkspaceEdge>>(null);
  const canvasRef = useRef<HTMLElement>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const patchTimersRef = useRef(new Map<string, number>());
  const mountedRef = useRef(true);

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
      setSaveState("saving");
      try {
        await patchDesignNode(projectId, nodeId, patch);
        if (mountedRef.current) setSaveState("saved");
      } catch {
        if (mountedRef.current) setSaveState("failed");
      }
    },
    [projectId],
  );

  const scheduleNodePatch = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      const currentTimer = patchTimersRef.current.get(nodeId);
      if (currentTimer !== undefined) window.clearTimeout(currentTimer);
      setSaveState("saving");
      const timer = window.setTimeout(() => {
        patchTimersRef.current.delete(nodeId);
        void persistNodePatch(nodeId, patch);
      }, 500);
      patchTimersRef.current.set(nodeId, timer);
    },
    [persistNodePatch],
  );

  const updateNodeData = useCallback(
    (nodeId: string, patch: Partial<WorkspaceNode["data"]>) => {
      setNodes((current) => {
        const next = current.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, ...patch } }
            : node,
        );
        nodesRef.current = next;
        return next;
      });
    },
    [],
  );

  const updatePrompt = useCallback(
    (nodeId: string, prompt: string) => {
      updateNodeData(nodeId, { prompt });
      scheduleNodePatch(nodeId, { prompt });
    },
    [scheduleNodePatch, updateNodeData],
  );

  const updateTitle = useCallback(
    (nodeId: string, title: string) => {
      setNodes((current) => {
        const previous = current.find((node) => node.id === nodeId)?.data.title;
        const next = current.map((node) => {
          if (node.id === nodeId) {
            return { ...node, data: { ...node.data, title } };
          }
          const currentSubject = node.data.subject;
          if (
            currentSubject !== null &&
            currentSubject.nodeTitle === previous
          ) {
            return {
              ...node,
              data: {
                ...node.data,
                subject: {
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
      scheduleNodePatch(nodeId, { title });
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
        void deleteDesignNode(projectId, nodeId).catch(() =>
          setSaveState("failed"),
        );
      }
    },
    [persistNodePatch, projectId],
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
        void deleteSubjectEdge(projectId, edge.target).catch(() =>
          setSaveState("failed"),
        );
      }
    },
    [projectId],
  );

  const onConnect = useCallback(
    async (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const source = nodesRef.current.find(
        (node) => node.id === connection.source,
      );
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
    [projectId, refreshWorkspace],
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
      const timer = patchTimersRef.current.get(nodeId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        patchTimersRef.current.delete(nodeId);
      }
      updateNodeData(nodeId, { runState: "running", runError: null });
      try {
        await patchDesignNode(projectId, nodeId, {
          prompt: node.data.prompt,
          title: node.data.title,
          settings: node.data.settings,
        });
        let job = await submitRun(projectId, nodeId, crypto.randomUUID());
        while (job.status !== "complete" && job.status !== "failed") {
          await new Promise((resolve) => window.setTimeout(resolve, 750));
          job = await getRun(projectId, job.id);
        }
        if (job.status === "failed") {
          throw new Error(job.error ?? "Run failed");
        }
        await refreshWorkspace();
        if (mountedRef.current) setSaveState("saved");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Run failed";
        if (mountedRef.current) {
          updateNodeData(nodeId, { runState: "failed", runError: message });
          setSaveState("failed");
        }
      }
    },
    [projectId, refreshWorkspace, updateNodeData],
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
    }),
    [
      branchVersion,
      runNode,
      selectVersion,
      updatePrompt,
      updateTitle,
      updateWhiteBackground,
    ],
  );

  return (
    <DesignNodeActionsContext.Provider value={actions}>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-white">
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
