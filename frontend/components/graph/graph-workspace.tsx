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
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import {
  nodeLabel,
  createBranch,
  createDesignNode,
  deleteSubjectEdge,
  deleteDesignNode,
  duplicateDesignNode,
  getGraph,
  getRun,
  patchDesignNode,
  replaceSubjectEdge,
  submitRun,
  savePrompt,
  saveMask,
  workspaceWires,
  runBlockingReason,
  runDisplay,
  type PromptPart,
  toWorkspaceGraph,
  type GraphDocument,
  type WorkspaceEdge,
  type WorkspaceNode,
  type Version,
} from "@/lib/graph";

import { RoleEdge } from "./role-edge";
import { ConfirmDialog, type Confirmation } from "./confirm-dialog";
import { AddNodeControl } from "./add-node-control";
import { DesignNode } from "./design-node";
import { HelpPanel } from "./help-panel";
import { MaskEditor } from "./mask-editor";
import { ImageViewer } from "./image-viewer";
import { MeshViewer } from "./mesh-viewer";
import { CollapseDialog } from "./collapse-dialog";
import { DesignNodeActionsContext } from "./design-node-actions";
import { SaveStatus, type SaveState } from "./save-status";

const nodeTypes = { design: DesignNode } satisfies NodeTypes;
const fitViewOptions = { padding: 0.2, maxZoom: 1, minZoom: 0.01 };
const edgeTypes = { role: RoleEdge };
const defaultEdgeOptions = { type: "role", interactionWidth: 24 };

function findAvailablePosition(
  origin: { x: number; y: number },
  nodes: WorkspaceNode[],
  direction?: "right" | "below",
): { x: number; y: number } {
  for (let radius = 0; radius < 10; radius += 1) {
    const offsets =
      radius === 0
        ? [{ column: 0, row: 0 }]
        : direction
          ? [
              {
                column: direction === "right" ? radius : 0,
                row: direction === "below" ? radius : 0,
              },
            ]
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
        x: origin.x + offset.column * 380,
        y: origin.y + offset.row * 850,
      };
      const overlaps = nodes.some(
        (node) =>
          candidate.x < node.position.x + (node.measured?.width ?? 304) + 32 &&
          candidate.x + 336 > node.position.x &&
          candidate.y < node.position.y + (node.measured?.height ?? 700) + 40 &&
          candidate.y + 740 > node.position.y,
      );
      if (!overlaps) return candidate;
    }
  }
  return {
    x: origin.x + (direction === "below" ? 0 : 3800),
    y: origin.y + (direction === "below" ? 8500 : 0),
  };
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
  const [hoveredWire, setHoveredWire] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const confirm = useCallback(
    (message: string, verb: string) =>
      new Promise<boolean>((resolve) =>
        setConfirmation({ message, verb, resolve }),
      ),
    [],
  );
  const disconnectingSubjects = useRef(new Set<string>());
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
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
  const refreshSequence = useRef(0);
  const deletingNodes = useRef(new Set<string>());
  const submittingNodes = useRef(new Set<string>());
  const allVersions = useRef(
    new Map(
      initialGraph.nodes
        .flatMap((node) => node.versions)
        .map((version) => [version.id, version]),
    ),
  );

  useEffect(() => {
    mountedRef.current = true;
    const timers = patchTimersRef.current;
    return () => {
      mountedRef.current = false;
      for (const timer of timers.values()) window.clearTimeout(timer);
    };
  }, []);

  const setNodeSaveState = useCallback((id: string, state: SaveState) => {
    const next = nodesRef.current.map((node) =>
      node.id === id
        ? { ...node, data: { ...node.data, saveState: state } }
        : node,
    );
    nodesRef.current = next;
    setNodes(next);
  }, []);

  const replaceWorkspace = useCallback((graph: GraphDocument) => {
    allVersions.current = new Map(
      graph.nodes
        .flatMap((node) => node.versions)
        .map((version) => [version.id, version]),
    );
    const workspace = toWorkspaceGraph(graph);
    workspace.nodes = workspace.nodes
      .filter((node) => !deletingNodes.current.has(node.id))
      .map((node) => {
        const current = nodesRef.current.find((item) => item.id === node.id);
        if (!current) return node;
        if (node.data.versions.length) {
          pendingDocuments.current.delete(node.id);
          const pending = pendingPatches.current.get(node.id);
          if (pending) {
            delete pending.settings;
            delete pending.seed;
            delete pending.prompt;
          }
        }
        const document = pendingDocuments.current.get(node.id);
        const patch = pendingPatches.current.get(node.id);
        return {
          ...node,
          selected: current.selected,
          measured: current.measured,
          dragging: current.dragging,
          position:
            current.dragging || patch?.position
              ? current.position
              : node.position,
          data: {
            ...node.data,
            ...(document
              ? {
                  document,
                  prompt: current.data.prompt,
                  connects: current.data.connects,
                }
              : {}),
            ...(patch?.title !== undefined
              ? { title: current.data.title }
              : {}),
            ...(patch?.settings !== undefined
              ? { settings: current.data.settings }
              : {}),
            revision:
              document || patch ? current.data.revision : node.data.revision,
            run:
              current.data.run.status === "running" &&
              (!current.data.run.job ||
                graph.nodes.find((item) => item.id === node.id)?.run?.id !==
                  current.data.run.job.id)
                ? current.data.run
                : node.data.run,
            ...(disconnectingSubjects.current.has(node.id)
              ? { subject: null, mask: null }
              : {}),
            meshPreview: current.data.meshPreview,
            previewMode: current.data.previewMode,
            draftError: node.data.versions.length
              ? null
              : current.data.draftError,
            saveState: current.data.draftError
              ? "failed"
              : document || patch
                ? "saving"
                : "saved",
          },
        };
      });
    for (const current of nodesRef.current) {
      if (
        !deletingNodes.current.has(current.id) &&
        !workspace.nodes.some((node) => node.id === current.id) &&
        (pendingDocuments.current.has(current.id) ||
          pendingPatches.current.has(current.id))
      ) {
        workspace.nodes.push({
          ...current,
          data: {
            ...current.data,
            remoteDeleted: true,
            draftError: "Node deleted — copy this text to a new node.",
          },
        });
      }
    }
    workspace.edges = workspaceWires(
      workspace.nodes,
      workspace.edges.filter(
        (edge) =>
          !disconnectingSubjects.current.has(edge.target) ||
          edge.data?.role !== "subject",
      ),
    ).map((edge) => ({
      ...edge,
      selected: edgesRef.current.find((current) => current.id === edge.id)
        ?.selected,
    }));
    nodesRef.current = workspace.nodes;
    edgesRef.current = workspace.edges;
    setNodes(workspace.nodes);
    setEdges(workspace.edges);
  }, []);

  const refreshWorkspace = useCallback(async () => {
    const sequence = ++refreshSequence.current;
    const graph = await getGraph(projectId);
    if (mountedRef.current && sequence === refreshSequence.current) {
      replaceWorkspace(graph);
      setConnectionError(null);
    }
  }, [projectId, replaceWorkspace]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible")
        void refreshWorkspace().catch(() =>
          setConnectionError(
            "Network interrupted. Your local draft is still here; checking again…",
          ),
        );
    }, 3000);
    return () => clearInterval(timer);
  }, [refreshWorkspace]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (pendingDocuments.current.size || pendingPatches.current.size) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

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
          setNodeSaveState(nodeId, "saving");
          const pending = pendingPatches.current.get(nodeId);
          const document = pendingDocuments.current.get(nodeId);
          if ((!pending && !document) || deletingNodes.current.has(nodeId))
            return;
          try {
            let revision = nodesRef.current.find((node) => node.id === nodeId)!
              .data.revision;
            if (pending && Object.keys(pending).length) {
              const result = await patchDesignNode(projectId, nodeId, {
                ...pending,
                expected_revision: revision,
              });
              revision = result.revision;
              nodesRef.current = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? {
                      ...node,
                      data: { ...node.data, revision, draftError: null },
                    }
                  : node,
              );
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
              const savedRevision = graph.nodes.find(
                (node) => node.id === nodeId,
              )!.revision;
              nodesRef.current = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? {
                      ...node,
                      data: {
                        ...node.data,
                        revision: savedRevision,
                        draftError: null,
                      },
                    }
                  : node,
              );
              replaceWorkspace(graph);
            } else {
              const updated = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? {
                      ...node,
                      data: { ...node.data, revision, draftError: null },
                    }
                  : node,
              );
              nodesRef.current = updated;
              setNodes(updated);
            }
            setNodeSaveState(
              nodeId,
              pendingDocuments.current.has(nodeId) ||
                pendingPatches.current.has(nodeId)
                ? "saving"
                : "saved",
            );
            if (mountedRef.current)
              setSaveState(
                pendingDocuments.current.size || pendingPatches.current.size
                  ? "saving"
                  : "saved",
              );
          } catch (error) {
            if (mountedRef.current) {
              setSaveState("failed");
              const message =
                error instanceof Error ? error.message : "Could not save";
              const updated = nodesRef.current.map((node) =>
                node.id === nodeId
                  ? { ...node, data: { ...node.data, draftError: message } }
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
    [projectId, replaceWorkspace, setNodeSaveState],
  );

  const scheduleNodePatch = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      pendingPatches.current.set(nodeId, {
        ...pendingPatches.current.get(nodeId),
        ...patch,
      });
      setNodeSaveState(nodeId, "saving");
      const currentTimer = patchTimersRef.current.get(nodeId);
      if (currentTimer !== undefined) window.clearTimeout(currentTimer);
      setSaveState("saving");
      const timer = window.setTimeout(() => {
        patchTimersRef.current.delete(nodeId);
        void persistNodePatch(nodeId, {}).catch(() => undefined);
      }, 500);
      patchTimersRef.current.set(nodeId, timer);
    },
    [persistNodePatch, setNodeSaveState],
  );

  const updateNodeData = useCallback(
    (nodeId: string, patch: Partial<WorkspaceNode["data"]>) => {
      const next = nodesRef.current.map((node) => {
        if (node.id === nodeId)
          return { ...node, data: { ...node.data, ...patch } };
        if ("activeVersionId" in patch)
          return {
            ...node,
            data: {
              ...node.data,
              connects: node.data.connects.map((ref) =>
                ref.nodeId === nodeId
                  ? {
                      ...ref,
                      versionId: patch.activeVersionId ?? null,
                      state: patch.activeVersionId
                        ? ("ready" as const)
                        : ("empty" as const),
                    }
                  : ref,
              ),
            },
          };
        return node;
      });
      nodesRef.current = next;
      setNodes(next);
    },
    [],
  );

  const focusNode = useCallback((id: string) => {
    const node = nodesRef.current.find((node) => node.id === id);
    if (!node) return;
    const selected = nodesRef.current.map((node) => ({
      ...node,
      selected: node.id === id,
    }));
    nodesRef.current = selected;
    setNodes(selected);
    void flowInstanceRef.current?.setCenter(
      node.position.x + 152,
      node.position.y + 200,
      { zoom: 1, duration: 350 },
    );
  }, []);

  const resolveDraft = useCallback(
    async (nodeId: string, keepMine: boolean) => {
      if (
        !keepMine &&
        !window.confirm("Discard this local draft and load the saved node?")
      )
        return;
      const timer = patchTimersRef.current.get(nodeId);
      if (timer !== undefined) {
        clearTimeout(timer);
        patchTimersRef.current.delete(nodeId);
      }
      await saves.current.get(nodeId)?.catch(() => undefined);
      try {
        const graph = await getGraph(projectId);
        const latest = graph.nodes.find((node) => node.id === nodeId);
        if (!latest || latest.deleted) {
          setConnectionError(
            "This node was deleted in another tab. Copy your draft before leaving.",
          );
          return;
        }
        if (!keepMine) {
          pendingDocuments.current.delete(nodeId);
          pendingPatches.current.delete(nodeId);
        }
        updateNodeData(nodeId, { revision: latest.revision, draftError: null });
        replaceWorkspace(graph);
        if (keepMine) await persistNodePatch(nodeId, {});
      } catch (error) {
        updateNodeData(nodeId, {
          draftError:
            error instanceof Error
              ? error.message
              : "Could not reload saved draft",
        });
      }
    },
    [projectId, persistNodePatch, replaceWorkspace, updateNodeData],
  );

  const duplicateNode = useCallback(
    async (nodeId: string) => {
      const node = nodesRef.current.find((node) => node.id === nodeId);
      if (!node) return;
      try {
        await persistNodePatch(nodeId, {});
        const duplicate = await duplicateDesignNode(
          projectId,
          nodeId,
          findAvailablePosition(
            { x: node.position.x + 500, y: node.position.y },
            nodesRef.current,
          ),
        );
        await refreshWorkspace();
        focusNode(duplicate.id);
      } catch (error) {
        updateNodeData(nodeId, {
          draftError:
            error instanceof Error
              ? error.message
              : "Could not duplicate draft",
        });
      }
    },
    [projectId, persistNodePatch, refreshWorkspace, updateNodeData, focusNode],
  );

  const updateDocument = useCallback(
    (nodeId: string, document: PromptPart[]) => {
      const draft = nodesRef.current.find((node) => node.id === nodeId);
      if (
        !draft ||
        draft.data.versions.length ||
        draft.data.run.status === "running" ||
        (draft.data.mask && document.some((part) => part.type === "connect"))
      )
        return;
      const current = nodesRef.current.find((node) => node.id === nodeId);
      if (!current) return;
      const connects = document.flatMap((part) => {
        if (part.type === "text") return [];
        const source = nodesRef.current.find(
          (node) => node.id === part.source_node_id,
        );
        return [
          {
            versionId: source?.data.activeVersionId ?? null,
            edgeId: part.edge_id,
            nodeId: part.source_node_id,
            title:
              (source ? nodeLabel(source.data) : undefined) ??
              current.data.connects.find((ref) => ref.edgeId === part.edge_id)
                ?.title ??
              "Deleted reference",
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
      const wires = workspaceWires(nodesRef.current, edgesRef.current);
      edgesRef.current = wires;
      setEdges(wires);
      scheduleNodePatch(nodeId, {});
    },
    [scheduleNodePatch, updateNodeData],
  );

  const updateTitle = useCallback(
    (nodeId: string, title: string) => {
      const label = nodeLabel({
        title,
        prompt: nodesRef.current.find((node) => node.id === nodeId)?.data.prompt ?? "",
      });
      const next = nodesRef.current.map((node) => ({
        ...node,
        data: {
          ...node.data,
          ...(node.id === nodeId ? { title } : {}),
          subject:
            node.data.subject?.nodeId === nodeId
              ? { ...node.data.subject, nodeTitle: label }
              : node.data.subject,
          connects: node.data.connects.map((ref) =>
            ref.nodeId === nodeId ? { ...ref, title: label } : ref,
          ),
        },
      }));
      nodesRef.current = next;
      setNodes(next);
      scheduleNodePatch(nodeId, { title });
    },
    [scheduleNodePatch],
  );

  const updateWhiteBackground = useCallback(
    (nodeId: string, enabled: boolean) => {
      const node = nodesRef.current.find(
        (candidate) => candidate.id === nodeId,
      );
      if (
        !node ||
        node.data.versions.length ||
        node.data.run.status === "running"
      )
        return;
      const settings = { ...node.data.settings, whiteBackground: enabled };
      updateNodeData(nodeId, { settings });
      scheduleNodePatch(nodeId, { settings });
    },
    [scheduleNodePatch, updateNodeData],
  );

  const disconnectSubject = useCallback(
    async (nodeId: string, approved = false) => {
      const node = nodesRef.current.find((node) => node.id === nodeId);
      if (!node?.data.subject) return;
      if (
        node.data.mask &&
        !approved &&
        !(await confirm(
          "Disconnect input? The saved area selection will be cleared.",
          "Disconnect",
        ))
      )
        return;
      const subject = node.data.subject;
      disconnectingSubjects.current.add(nodeId);
      updateNodeData(nodeId, { subject: null, mask: null });
      const remaining = edgesRef.current.filter(
        (edge) => edge.target !== nodeId || edge.data?.role !== "subject",
      );
      edgesRef.current = workspaceWires(nodesRef.current, remaining);
      setEdges(edgesRef.current);
      try {
        await saves.current.get(nodeId)?.catch(() => undefined);
        // Clear first: a failed disconnect can keep its subject, never a stranded mask.
        if (node.data.mask) await saveMask(projectId, nodeId, null);
        await deleteSubjectEdge(projectId, nodeId);
        disconnectingSubjects.current.delete(nodeId);
        await refreshWorkspace();
      } catch {
        disconnectingSubjects.current.delete(nodeId);
        updateNodeData(nodeId, {
          subject,
          draftError: "Disconnect failed — try again.",
        });
        await refreshWorkspace().catch(() => setSaveState("failed"));
      }
    },
    [confirm, projectId, refreshWorkspace, updateNodeData],
  );

  const onNodesChange = useCallback(
    (changes: NodeChange<WorkspaceNode>[]) => {
      const removedIds = changes
        .filter((change) => change.type === "remove")
        .map((change) => change.id);
      const removedNodes = nodesRef.current.filter((node) =>
        removedIds.includes(node.id),
      );
      const settledPositions = changes.filter(
        (change) => change.type === "position" && change.dragging === false,
      );
      const next = applyNodeChanges(changes, nodesRef.current).map((node) => ({
        ...node,
        data: {
          ...node.data,
          subject:
            node.data.subject && removedIds.includes(node.data.subject.nodeId)
              ? { ...node.data.subject, deleted: true }
              : node.data.subject,
          connects: node.data.connects.map((ref) =>
            removedIds.includes(ref.nodeId)
              ? { ...ref, state: "deleted" as const }
              : ref,
          ),
        },
      }));
      nodesRef.current = next;
      setNodes(next);
      for (const change of settledPositions) {
        if (change.type === "position" && change.position) {
          void persistNodePatch(change.id, { position: change.position }).catch(
            () => undefined,
          );
        }
      }
      for (const node of removedNodes) {
        // Remote-deleted drafts only exist locally; removing one needs no server mutation.
        const removal = (saves.current.get(node.id) ?? Promise.resolve())
          .catch(() => undefined)
          .then(() =>
            node.data.remoteDeleted
              ? undefined
              : deleteDesignNode(projectId, node.id),
          );
        void removal
          .then(() => {
            pendingDocuments.current.delete(node.id);
            pendingPatches.current.delete(node.id);
            saves.current.delete(node.id);
            deletingNodes.current.delete(node.id);
            setSaveState(
              pendingDocuments.current.size || pendingPatches.current.size
                ? "saving"
                : "saved",
            );
            void refreshWorkspace().catch(() => setSaveState("failed"));
          })
          .catch(() => {
            deletingNodes.current.delete(node.id);
            const restored = [...nodesRef.current, node];
            nodesRef.current = restored;
            setNodes(restored);
            setSaveState("failed");
            void refreshWorkspace().catch(() => undefined);
          });
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
      const next = applyEdgeChanges(changes, edgesRef.current);
      edgesRef.current = next;
      setEdges(next);
      for (const edge of removed) {
        if (
          deletingNodes.current.has(edge.source) ||
          deletingNodes.current.has(edge.target) ||
          (edge.data?.state !== "deleted" &&
            !nodesRef.current.some((node) => node.id === edge.source)) ||
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
        void disconnectSubject(edge.target, true);
      }
    },
    [disconnectSubject, updateDocument],
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
    const position = findAvailablePosition(
      { x: flowPosition.x - 152, y: flowPosition.y - 300 },
      nodesRef.current,
    );
    setSaveState("saving");
    try {
      const created = await createDesignNode(projectId, {
        id: crypto.randomUUID(),
        position,
      });
      await refreshWorkspace();
      focusNode(created.id);
      if (mountedRef.current) setSaveState("saved");
    } catch {
      if (mountedRef.current) setSaveState("failed");
    }
  }, [projectId, refreshWorkspace, focusNode]);

  const selectVersion = useCallback(
    (nodeId: string, versionId: string) => {
      updateNodeData(nodeId, { activeVersionId: versionId });
      void persistNodePatch(nodeId, { active_version_id: versionId }).catch(
        () => undefined,
      );
    },
    [persistNodePatch, updateNodeData],
  );

  const branchVersion = useCallback(
    async (nodeId: string, versionId: string) => {
      const source = nodesRef.current.find((node) => node.id === nodeId);
      if (!source) return;
      const preferred = { x: source.position.x + 380, y: source.position.y };
      const position = findAvailablePosition(
        preferred,
        nodesRef.current,
        "right",
      );
      setSaveState("saving");
      try {
        const created = await createBranch(projectId, versionId, {
          id: crypto.randomUUID(),
          position,
        });
        await refreshWorkspace();
        focusNode(created.node.id);
        focusPrompt(created.node.id);
        if (mountedRef.current) setSaveState("saved");
      } catch {
        if (mountedRef.current) setSaveState("failed");
      }
    },
    [projectId, refreshWorkspace, focusNode],
  );

  const runNode = useCallback(
    async (nodeId: string) => {
      const node = nodesRef.current.find(
        (candidate) => candidate.id === nodeId,
      );
      if (
        !node ||
        runBlockingReason(node.data) ||
        submittingNodes.current.has(nodeId)
      )
        return;
      submittingNodes.current.add(nodeId);
      const timer = patchTimersRef.current.get(nodeId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        patchTimersRef.current.delete(nodeId);
      }
      try {
        await persistNodePatch(nodeId, {});
        const current = nodesRef.current.find(
          (candidate) => candidate.id === nodeId,
        );
        if (!current) return;
        // A locally selected reference image must reach the server before it
        // resolves this node's preview and freezes the run inputs.
        await Promise.all(
          current.data.connects
            .filter(
              (ref) =>
                pendingPatches.current.get(ref.nodeId)?.active_version_id !==
                undefined,
            )
            .map((ref) => saves.current.get(ref.nodeId)),
        );
        updateNodeData(nodeId, {
          run: {
            status: "running",
            job: null,
            startedAt: new Date().toISOString(),
          },
        });
        let job = await submitRun(projectId, nodeId, crypto.randomUUID());
        updateNodeData(nodeId, { run: runDisplay(job) });
        while (
          mountedRef.current &&
          job.status !== "complete" &&
          job.status !== "failed"
        ) {
          await new Promise((resolve) => window.setTimeout(resolve, 750));
          try {
            job = await getRun(projectId, job.id);
            updateNodeData(nodeId, { run: runDisplay(job) });
          } catch {
            setConnectionError(
              "The run is saved, but its status is temporarily unavailable. Checking again…",
            );
          }
        }
        if (!mountedRef.current) return;
        if (job.status === "failed") {
          throw new Error(job.error ?? "Run failed");
        }
        updateNodeData(nodeId, { run: { status: "idle" } });
        await refreshWorkspace();
        if (mountedRef.current) setSaveState("saved");
        return job.version_id ?? undefined;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Run failed";
        if (mountedRef.current) {
          updateNodeData(nodeId, { run: { status: "failed", message } });
        }
      } finally {
        submittingNodes.current.delete(nodeId);
      }
    },
    [projectId, refreshWorkspace, updateNodeData, persistNodePatch],
  );

  const actions = useMemo(
    () => ({
      updateTitle,
      updateWhiteBackground,
      selectVersion,
      branchVersion,
      runNode,
      editMask: setMaskNodeId,
      removeMask: async (id: string) => {
        try {
          await saveMask(projectId, id, null);
          updateNodeData(id, { mask: null });
        } catch (error) {
          setConnectionError(
            error instanceof Error
              ? error.message
              : "Could not remove selection",
          );
        }
      },
      disconnectSubject,
      deleteWire: (id: string) => {
        void flowInstanceRef.current?.deleteElements({ edges: [{ id }] });
      },
      duplicateNode,
      deleteNode: (id: string) => {
        void flowInstanceRef.current?.deleteElements({ nodes: [{ id }] });
      },
      resolveDraft,
      collapseVersion: setCollapseVersionId,
      viewMesh: (id: string) =>
        setMeshVersion(
          nodesRef.current
            .flatMap((node) => node.data.versions)
            .find((version) => version.id === id) ?? null,
        ),
      viewImage: (nodeId: string) =>
        updateNodeData(nodeId, { previewMode: "image" }),
      showMesh: (nodeId: string) =>
        updateNodeData(nodeId, { previewMode: "mesh" }),
      viewVersions: (ids: string[]) =>
        setViewedVersions(
          ids.flatMap((id) => {
            const version = allVersions.current.get(id);
            return version ? [version] : [];
          }),
        ),
      updateDocument,
      candidates: (id: string) =>
        nodesRef.current
          .filter((node) => node.id !== id)
          .map((node) => ({ id: node.id, title: nodeLabel(node.data) })),
      hoverWire: setHoveredWire,
      jumpNode: focusNode,
    }),
    [
      branchVersion,
      disconnectSubject,
      runNode,
      selectVersion,
      updateTitle,
      updateWhiteBackground,
      updateDocument,
      projectId,
      updateNodeData,
      duplicateNode,
      resolveDraft,
      focusNode,
    ],
  );

  const keydown = (event: KeyboardEvent<HTMLElement>) => {
    if (
      (event.target instanceof HTMLElement &&
        event.target.closest(
          'input,textarea,select,[contenteditable="true"]',
        )) ||
      document.querySelector("dialog[open]")
    )
      return;
    if (event.key === "Escape") {
      setHoveredWire(null);
      return;
    }
    const selected = nodesRef.current.find((node) => node.selected);
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && selected) {
      event.preventDefault();
      void runNode(selected.id);
    }
    if (event.key.toLowerCase() === "n" && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      void addNode();
    }
    if (event.key.toLowerCase() === "f" && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      void flowInstanceRef.current?.fitView(fitViewOptions);
    }
    if (
      event.key.toLowerCase() === "d" &&
      (event.metaKey || event.ctrlKey) &&
      selected
    ) {
      event.preventDefault();
      if (!selected.data.versions.length) void duplicateNode(selected.id);
    }
    if (
      event.key.toLowerCase() === "b" &&
      !event.metaKey &&
      !event.ctrlKey &&
      selected?.data.activeVersionId
    ) {
      event.preventDefault();
      void branchVersion(selected.id, selected.data.activeVersionId);
    }
  };

  const activeWire =
    hoveredWire ?? edges.find((edge) => edge.selected)?.id ?? null;
  const displayEdges = workspaceWires(nodes, edges).map((edge) => ({
    ...edge,
    data: edge.data
      ? {
          ...edge.data,
          highlighted: edge.id === activeWire,
          dimmed: !!activeWire && edge.id !== activeWire,
        }
      : edge.data,
  }));
  const highlighted = displayEdges.find((edge) => edge.id === activeWire);
  const displayNodes = nodes.map((node) => ({
    ...node,
    style: { ...node.style, borderRadius: "6px" },
    data: {
      ...node.data,
      highlightedWireId: activeWire,
      wireHighlighted:
        !!highlighted &&
        (node.id === highlighted.source || node.id === highlighted.target),
    },
  }));

  return (
    <DesignNodeActionsContext.Provider value={actions}>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-white">
        {helpOpen ? <HelpPanel onClose={() => setHelpOpen(false)} /> : null}
        {confirmation ? (
          <ConfirmDialog
            confirmation={confirmation}
            onClose={() => setConfirmation(null)}
          />
        ) : null}
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
                updateNodeData(node.id, {
                  meshPreview: { versionId, url },
                  previewMode: "mesh",
                });
            }}
          />
        ) : null}
        {viewedVersions.length > 0 ? (
          <ImageViewer
            versions={viewedVersions}
            nodeNames={Object.fromEntries(
              nodes.map((node) => [node.id, nodeLabel(node.data)]),
            )}
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
              hasReferences={node.data.connects.length > 0}
              onClose={() => setMaskNodeId(null)}
              onSave={(mask) => {
                updateNodeData(node.id, { mask });
                setMaskNodeId(null);
                focusPrompt(node.id);
              }}
            />
          ) : null;
        })()}
        <header className="grid h-14 shrink-0 grid-cols-[1fr_minmax(0,auto)_1fr] items-center border-b border-border px-4 sm:px-6">
          <Link
            className="w-fit text-sm font-medium text-neutral-600 hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            href="/"
            onClick={(event) => {
              if (
                (pendingDocuments.current.size ||
                  pendingPatches.current.size) &&
                !window.confirm(
                  "Some draft changes are not saved. Leave this canvas?",
                )
              )
                event.preventDefault();
            }}
          >
            ← Projects
          </Link>
          <h1 className="max-w-[45vw] truncate text-sm font-semibold text-foreground">
            {projectName}
          </h1>
          <SaveStatus state={saveState} />
        </header>
        {connectionError ? (
          <p
            role="alert"
            className="bg-amber-50 px-5 py-2 text-xs text-amber-900"
          >
            {connectionError}
          </p>
        ) : null}
        <main
          aria-label="Project graph workspace"
          className="min-h-0 flex-1"
          ref={canvasRef}
          tabIndex={0}
          onKeyDownCapture={keydown}
        >
          <ReactFlow<WorkspaceNode, WorkspaceEdge>
            defaultEdgeOptions={defaultEdgeOptions}
            edgeTypes={edgeTypes}
            connectOnClick
            isValidConnection={(connection) => {
              const source = nodesRef.current.find(
                (node) => node.id === connection.source,
              );
              const target = nodesRef.current.find(
                (node) => node.id === connection.target,
              );
              if (
                !source ||
                !target ||
                source.id === target.id ||
                target.data.versions.length > 0 ||
                target.data.run.status === "running" ||
                (connection.targetHandle === "connect" && !!target.data.mask) ||
                connection.sourceHandle !== connection.targetHandle
              )
                return false;
              return connection.targetHandle === "subject"
                ? !!source.data.activeVersionId
                : target.data.connects.length < 2 &&
                    !target.data.connects.some(
                      (ref) => ref.nodeId === source.id,
                    );
            }}
            onEdgeMouseEnter={(_, edge) => setHoveredWire(edge.id)}
            onEdgeMouseLeave={(event, edge) => {
              if (
                event.relatedTarget instanceof Element &&
                event.relatedTarget.closest(`[data-wire-id="${edge.id}"]`)
              )
                return;
              setHoveredWire((current) =>
                current === edge.id ? null : current,
              );
            }}
            deleteKeyCode={
              confirmation ||
              maskNodeId ||
              viewedVersions.length > 0 ||
              collapseVersionId ||
              meshVersion
                ? null
                : ["Backspace", "Delete"]
            }
            edges={displayEdges}
            fitView
            fitViewOptions={fitViewOptions}
            nodeTypes={nodeTypes}
            nodes={displayNodes}
            onlyRenderVisibleElements
            minZoom={0.01}
            maxZoom={2}
            selectionOnDrag={false}
            multiSelectionKeyCode="Shift"
            panActivationKeyCode="Space"
            panOnDrag
            onConnect={(connection) => void onConnect(connection)}
            onEdgesChange={onEdgesChange}
            onInit={(instance) => {
              flowInstanceRef.current = instance;
            }}
            onNodesChange={onNodesChange}
            onPaneClick={() => canvasRef.current?.focus()}
            onBeforeDelete={async ({ nodes: removing, edges: connections }) => {
              if (
                connections.some(
                  (edge) =>
                    !removing.some(
                      (node) =>
                        node.id === edge.target || node.id === edge.source,
                    ) &&
                    nodesRef.current.some(
                      (node) =>
                        node.id === edge.target &&
                        (node.data.versions.length > 0 ||
                          node.data.run.status === "running"),
                    ),
                )
              )
                return false;
              if (document.querySelector("dialog[open]")) return false;
              const explicitConnections = connections.filter(
                (edge) =>
                  !removing.some(
                    (node) =>
                      node.id === edge.source || node.id === edge.target,
                  ),
              );
              let message: string | null = null;
              let verb = "Delete node";
              if (removing.length + explicitConnections.length > 1) {
                message = `Delete ${removing.length} nodes and ${explicitConnections.length} wires?`;
                verb = "Delete";
              } else if (removing.length === 1) {
                const node = removing[0];
                const count = node.data.versions.length;
                const dependents = nodesRef.current.filter(
                  (target) =>
                    target.id !== node.id &&
                    (target.data.subject?.nodeId === node.id ||
                      target.data.connects.some(
                        (ref) => ref.nodeId === node.id,
                      )),
                ).length;
                if (count || dependents)
                  message = dependents
                    ? `Delete "${nodeLabel(node.data)}"? Its ${count} ${count === 1 ? "image stays" : "images stay"} available to the ${dependents} ${dependents === 1 ? "node" : "nodes"} using them.`
                    : `Delete "${nodeLabel(node.data)}"? Its ${count} ${count === 1 ? "image" : "images"} will no longer appear on the canvas.`;
                else if (
                  pendingDocuments.current.has(node.id) ||
                  pendingPatches.current.has(node.id)
                )
                  message =
                    "Delete this node? Unsaved changes to the prompt will be lost.";
              } else if (
                connections.some(
                  (edge) =>
                    edge.data?.role === "subject" &&
                    nodesRef.current.find((node) => node.id === edge.target)
                      ?.data.mask,
                )
              ) {
                message =
                  "Disconnect input? The saved area selection will be cleared.";
                verb = "Disconnect";
              }
              const approved = !message || (await confirm(message, verb));
              if (approved) {
                for (const node of removing) {
                  deletingNodes.current.add(node.id);
                  const timer = patchTimersRef.current.get(node.id);
                  if (timer !== undefined) clearTimeout(timer);
                  patchTimersRef.current.delete(node.id);
                }
              }
              return approved;
            }}
          >
            <Background
              color="#d4d4d8"
              gap={20}
              size={1}
              variant={BackgroundVariant.Dots}
            />
            {nodes.length > 0 ? (
              <Panel position="top-left">
                <AddNodeControl onAdd={() => void addNode()} />
                {nodes.filter((node) => node.selected).length === 2 &&
                nodes
                  .filter((node) => node.selected)
                  .every((node) => node.data.activeVersionId) ? (
                  <button
                    className="mt-2 rounded border bg-white px-3 py-2 text-sm"
                    onClick={() =>
                      actions.viewVersions(
                        nodes
                          .filter((node) => node.selected)
                          .map((node) => node.data.activeVersionId!),
                      )
                    }
                  >
                    Compare
                  </button>
                ) : null}
              </Panel>
            ) : null}
            <Panel position="bottom-right">
              <button
                onClick={() => setHelpOpen(true)}
                aria-label="Keyboard shortcuts"
                title="N: New node; B: New connected node; Cmd/Ctrl D: Duplicate draft; F: Fit; Left-drag: Pan; Shift: Select; Delete: Delete; Cmd/Ctrl Enter: Run; @: Reference; Escape: Close"
                className="rounded border bg-white px-2 py-1 text-neutral-500"
              >
                ?
              </button>
            </Panel>
            {nodes.length === 0 ? (
              <Panel position="top-center">
                <div className="mt-20 max-w-sm rounded-xl border bg-white p-5 text-center shadow-sm">
                  <p>1. Describe a design.</p>
                  <p>2. Run to generate it.</p>
                  <p>3. Add a connected node to change it.</p>
                  <button
                    className="mt-3 rounded bg-neutral-900 px-4 py-2 text-sm text-white"
                    onClick={() => void addNode()}
                  >
                    Add node
                  </button>
                </div>
              </Panel>
            ) : null}
            <Controls showInteractive={false} />
          </ReactFlow>
        </main>
      </div>
    </DesignNodeActionsContext.Provider>
  );
}

function focusPrompt(id: string) {
  window.setTimeout(() => {
    const root = document.querySelector<HTMLElement>(
      `[data-id="${id}"] [role="textbox"]`,
    );
    root?.focus();
    if (root) {
      const range = document.createRange();
      range.selectNodeContents(root);
      range.collapse(false);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  }, 150);
}
