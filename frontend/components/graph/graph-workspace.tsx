"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  Panel,
  ReactFlow,
  addEdge,
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
  saveGraph,
  toGraphDocument,
  toWorkspaceEdges,
  toWorkspaceNodes,
  type GraphDocument,
  type GraphNodeType,
  type WorkspaceEdge,
  type WorkspaceNode,
} from "@/lib/graph";

import { AddNodeControl } from "./add-node-control";
import { ImageNode } from "./image-node";
import { ModelNode } from "./model-node";
import { PromptNode } from "./prompt-node";
import { PromptNodeActionsContext } from "./prompt-node-actions";
import { SaveStatus, type SaveState } from "./save-status";

const nodeTypes = {
  prompt: PromptNode,
  image: ImageNode,
  model3d: ModelNode,
} satisfies NodeTypes;

const fitViewOptions = { padding: 0.2, maxZoom: 1 };
const defaultEdgeOptions = {
  style: { stroke: "#a1a1aa", strokeWidth: 1.5 },
};

function findAvailablePosition(
  center: { x: number; y: number },
  nodes: WorkspaceNode[],
): { x: number; y: number } {
  const origin = { x: center.x - 120, y: center.y - 70 };
  const offsets = [{ column: 0, row: 0 }];

  for (let radius = 1; radius < 10; radius += 1) {
    offsets.push(
      { column: radius, row: 0 },
      { column: -radius, row: 0 },
      { column: 0, row: radius },
      { column: 0, row: -radius },
      { column: radius, row: radius },
      { column: -radius, row: radius },
      { column: radius, row: -radius },
      { column: -radius, row: -radius },
    );
  }

  for (const offset of offsets) {
    const candidate = {
      x: origin.x + offset.column * 280,
      y: origin.y + offset.row * 190,
    };
    const overlapsNode = nodes.some(
      (node) =>
        Math.abs(node.position.x - candidate.x) < 250 &&
        Math.abs(node.position.y - candidate.y) < 160,
    );

    if (!overlapsNode) {
      return candidate;
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
  const initialNodes = useMemo(
    () => toWorkspaceNodes(initialGraph.nodes),
    [initialGraph.nodes],
  );
  const initialEdges = useMemo(
    () => toWorkspaceEdges(initialGraph.edges),
    [initialGraph.edges],
  );
  const [nodes, setNodes] = useState<WorkspaceNode[]>(initialNodes);
  const [edges, setEdges] = useState<WorkspaceEdge[]>(initialEdges);
  const [saveRevision, setSaveRevision] = useState(0);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const flowInstanceRef =
    useRef<ReactFlowInstance<WorkspaceNode, WorkspaceEdge>>(null);
  const canvasRef = useRef<HTMLElement>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const saveRevisionRef = useRef(0);
  const saveInFlightRef = useRef(false);
  const saveQueuedRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  const markDirty = useCallback(() => {
    saveRevisionRef.current += 1;
    setSaveRevision(saveRevisionRef.current);
    setSaveState("saving");
  }, []);

  const persistLatestGraph = useCallback(async () => {
    if (saveInFlightRef.current) {
      saveQueuedRef.current = true;
      return;
    }

    saveInFlightRef.current = true;

    while (true) {
      const revision = saveRevisionRef.current;
      const graph = toGraphDocument(nodesRef.current, edgesRef.current);
      saveQueuedRef.current = false;

      try {
        await saveGraph(projectId, graph);

        if (mountedRef.current && saveRevisionRef.current === revision) {
          setSaveState("saved");
        }
      } catch {
        if (mountedRef.current && saveRevisionRef.current === revision) {
          setSaveState("failed");
        }
      }

      if (!saveQueuedRef.current && saveRevisionRef.current === revision) {
        break;
      }
    }

    saveInFlightRef.current = false;
  }, [projectId]);

  useEffect(() => {
    if (saveRevision === 0) {
      return;
    }

    const saveTimer = window.setTimeout(() => {
      void persistLatestGraph();
    }, 700);

    return () => window.clearTimeout(saveTimer);
  }, [persistLatestGraph, saveRevision]);

  const onNodesChange = useCallback(
    (changes: NodeChange<WorkspaceNode>[]) => {
      setNodes((currentNodes) => {
        const nextNodes = applyNodeChanges(changes, currentNodes);
        nodesRef.current = nextNodes;
        return nextNodes;
      });

      if (
        changes.some(
          (change) =>
            change.type === "remove" ||
            (change.type === "position" && change.dragging === false),
        )
      ) {
        markDirty();
      }
    },
    [markDirty],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<WorkspaceEdge>[]) => {
      setEdges((currentEdges) => {
        const nextEdges = applyEdgeChanges(changes, currentEdges);
        edgesRef.current = nextEdges;
        return nextEdges;
      });

      if (changes.some((change) => change.type === "remove")) {
        markDirty();
      }
    },
    [markDirty],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((currentEdges) => {
        const nextEdges = addEdge(
          { ...connection, id: crypto.randomUUID() },
          currentEdges,
        );
        edgesRef.current = nextEdges;
        return nextEdges;
      });
      markDirty();
    },
    [markDirty],
  );

  const updatePromptText = useCallback(
    (nodeId: string, text: string) => {
      setNodes((currentNodes) => {
        const nextNodes = currentNodes.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, text } }
            : node,
        );
        nodesRef.current = nextNodes;
        return nextNodes;
      });
      markDirty();
    },
    [markDirty],
  );

  const addNode = useCallback(
    (type: GraphNodeType) => {
      const canvasBounds = canvasRef.current?.getBoundingClientRect();
      const screenPosition = {
        x: canvasBounds ? canvasBounds.left + canvasBounds.width / 2 : 320,
        y: canvasBounds ? canvasBounds.top + canvasBounds.height / 2 : 240,
      };
      const flowPosition = flowInstanceRef.current?.screenToFlowPosition(
        screenPosition,
      ) ?? { x: 0, y: 0 };
      const node: WorkspaceNode = {
        id: crypto.randomUUID(),
        type,
        position: findAvailablePosition(flowPosition, nodesRef.current),
        data: type === "prompt" ? { text: "" } : {},
      };

      setNodes((currentNodes) => {
        const nextNodes = [...currentNodes, node];
        nodesRef.current = nextNodes;
        return nextNodes;
      });
      markDirty();
    },
    [markDirty],
  );

  return (
    <PromptNodeActionsContext.Provider value={updatePromptText}>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-white">
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
            onConnect={onConnect}
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
              <AddNodeControl onAdd={addNode} />
            </Panel>
            <Controls showInteractive={false} />
          </ReactFlow>
        </main>
      </div>
    </PromptNodeActionsContext.Provider>
  );
}
