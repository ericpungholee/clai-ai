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
  runDisplay,
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
  origin: { x: number; y: number },
  nodes: WorkspaceNode[],
): { x: number; y: number } {
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
  const [connectionError, setConnectionError] = useState<string | null>(null);
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

  const replaceWorkspace = useCallback((graph: GraphDocument) => {
    allVersions.current = new Map(
      graph.nodes
        .flatMap((node) => node.versions)
        .map((version) => [version.id, version]),
    );
    const workspace = toWorkspaceGraph(graph);
    workspace.nodes = workspace.nodes.map((node) => {
      const current = nodesRef.current.find((item) => item.id === node.id);
      if (!current) return node;
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
          ...(patch?.title !== undefined ? { title: current.data.title } : {}),
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
          meshPreview: current.data.meshPreview,
          draftError: current.data.draftError,
        },
      };
    });
    for (const current of nodesRef.current) {
      if (
        !workspace.nodes.some((node) => node.id === current.id) &&
        (pendingDocuments.current.has(current.id) ||
          pendingPatches.current.has(current.id))
      ) {
        workspace.nodes.push({
          ...current,
          data: {
            ...current.data,
            remoteDeleted: true,
            draftError:
              "Deleted in another tab. Copy this local draft before removing the node; it can no longer run.",
          },
        });
      }
    }
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
            "Connection interrupted. Your local draft is still here; checking again…",
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
      const removedNodes = nodesRef.current.filter((node) =>
        removedIds.includes(node.id),
      );
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
          void persistNodePatch(change.id, { position: change.position }).catch(
            () => undefined,
          );
        }
      }
      for (const node of removedNodes) {
        // Remote-deleted drafts only exist locally; removing one needs no server mutation.
        const removal = node.data.remoteDeleted
          ? Promise.resolve()
          : deleteDesignNode(projectId, node.id);
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
      setEdges((current) => {
        const next = applyEdgeChanges(changes, current);
        edgesRef.current = next;
        return next;
      });
      for (const edge of removed) {
        if (
          deletingNodes.current.has(edge.source) ||
          deletingNodes.current.has(edge.target) ||
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
      const position = findAvailablePosition(preferred, nodesRef.current);
      setSaveState("saving");
      try {
        const created = await createBranch(projectId, versionId, {
          id: crypto.randomUUID(),
          position,
        });
        await refreshWorkspace();
        focusNode(created.node.id);
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
      if (!node || !node.data.prompt.trim()) return;
      if (node.data.run.status === "running") return;
      const timer = patchTimersRef.current.get(nodeId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
        patchTimersRef.current.delete(nodeId);
      }
      updateNodeData(nodeId, {
        run: {
          status: "running",
          job: null,
          startedAt: new Date().toISOString(),
        },
      });
      try {
        await persistNodePatch(nodeId, {});
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
        updateNodeData(nodeId, { meshPreview: null }),
      viewVersions: (ids: string[]) =>
        setViewedVersions(
          ids.flatMap((id) => {
            const version = allVersions.current.get(id);
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
      jumpNode: focusNode,
    }),
    [
      branchVersion,
      runNode,
      selectVersion,
      updateTitle,
      updateWhiteBackground,
      updateDocument,
      projectId,
      refreshWorkspace,
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
    const selected = nodesRef.current.find((node) => node.selected);
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
      void duplicateNode(selected.id);
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
            deleteKeyCode={
              maskNodeId ||
              viewedVersions.length > 0 ||
              collapseVersionId ||
              meshVersion
                ? null
                : ["Backspace", "Delete"]
            }
            edges={edges}
            fitView
            fitViewOptions={fitViewOptions}
            nodeTypes={nodeTypes}
            nodes={nodes}
            onlyRenderVisibleElements
            minZoom={0.1}
            maxZoom={2}
            selectionOnDrag
            multiSelectionKeyCode="Shift"
            panActivationKeyCode="Space"
            panOnDrag={[1, 2]}
            onConnect={(connection) => void onConnect(connection)}
            onEdgesChange={onEdgesChange}
            onInit={(instance) => {
              flowInstanceRef.current = instance;
            }}
            onNodesChange={onNodesChange}
            onPaneClick={() => canvasRef.current?.focus()}
            onBeforeDelete={async ({ nodes: removing }) => {
              const approved =
                removing.length === 0 ||
                (!edgesRef.current.some((edge) =>
                  removing.some((node) => node.id === edge.source),
                ) &&
                  !removing.some(
                    (node) =>
                      pendingDocuments.current.has(node.id) ||
                      pendingPatches.current.has(node.id),
                  )) ||
                window.confirm(
                  "Delete these concepts and their unsaved drafts? Connected prompts will keep broken chips until you replace or remove them. Historical images are retained.",
                );
              if (approved) {
                deletingNodes.current = new Set(
                  removing.map((node) => node.id),
                );
                for (const node of removing) {
                  const timer = patchTimersRef.current.get(node.id);
                  if (timer !== undefined) clearTimeout(timer);
                  patchTimersRef.current.delete(node.id);
                }
                await Promise.all(
                  removing.map((node) =>
                    saves.current.get(node.id)?.catch(() => undefined),
                  ),
                );
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
            <Panel position="top-left">
              <AddNodeControl onAdd={() => void addNode()} />
            </Panel>
            <Panel position="bottom-right">
              <p className="rounded bg-white/90 px-3 py-2 text-[10px] text-neutral-500">
                N new · B branch · ⌘/Ctrl D duplicate · F fit · Shift select ·
                Space drag to pan · Delete
              </p>
            </Panel>
            {nodes.length === 0 ? (
              <Panel position="top-center">
                <div className="mt-20 max-w-sm rounded-xl border bg-white p-5 text-center shadow-sm">
                  <h2 className="font-semibold">Start with one object</h2>
                  <p className="mt-2 text-sm text-neutral-500">
                    Add a node, describe a product, and run it. Branch from a
                    good image to explore another direction.
                  </p>
                  <button
                    className="mt-3 rounded bg-neutral-900 px-4 py-2 text-sm text-white"
                    onClick={() => void addNode()}
                  >
                    Add your first node
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
