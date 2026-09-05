import {
  Handle,
  Position,
  useConnection,
  useStore,
  useUpdateNodeInternals,
} from "@xyflow/react";
import { useEffect, type ReactNode } from "react";
import { nodeIsBlocked, type DesignNodeData } from "@/lib/graph";

export function NodeHandle({
  data,
  id,
  role,
  type,
  fallback = false,
}: {
  data: DesignNodeData;
  id: string;
  role: "subject" | "connect";
  type: "target" | "source";
  fallback?: boolean;
}) {
  const connection = useConnection();
  const available =
    type === "source"
      ? role === "connect" || !!data.activeVersionId
      : !data.versions.length &&
        data.run.status !== "running" &&
        (role === "subject" || (!data.mask && data.connects.length < 2));
  const validDrag =
    connection.inProgress &&
    type === "target" &&
    connection.fromNode?.id !== id &&
    connection.fromHandle?.id === role &&
    available &&
    !data.connects.some(
      (ref) => role === "connect" && ref.nodeId === connection.fromNode?.id,
    );
  const label = `${type === "source" ? "Start" : "Add"} ${role === "subject" ? "input image" : "reference"}`;
  return (
    <Handle
      id={role}
      type={type}
      position={type === "target" ? Position.Left : Position.Right}
      className={`wire-handle wire-${role === "connect" ? "reference" : "subject"} ${fallback ? "subject-fallback" : ""} ${available ? "available" : ""} ${validDrag ? "valid-drop" : ""}`}
      data-dragging={connection.inProgress || undefined}
      aria-label={label}
      title={label}
      tabIndex={available ? 0 : -1}
      role="button"
      isConnectable={available}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          event.stopPropagation();
          event.currentTarget.click();
        }
      }}
    />
  );
}

export function NodeFrame({
  children,
  selected,
  title,
  menu,
  data,
  id,
}: {
  children: ReactNode;
  selected: boolean;
  title: ReactNode;
  menu: ReactNode;
  data: DesignNodeData;
  id: string;
}) {
  const updateInternals = useUpdateNodeInternals();
  const needsMeasurement = useStore((state) => {
    const node = state.nodeLookup.get(id);
    return !!node?.measured.width && !node.internals.handleBounds;
  });
  useEffect(() => {
    // A controlled data update can arrive between the initial measurement and
    // its state commit. Recover bounds even when the card did not resize again.
    if (needsMeasurement) updateInternals(id);
  }, [id, needsMeasurement, updateInternals]);
  return (
    <div
      onTransitionEnd={(event) => {
        if (event.propertyName === "height") updateInternals(id);
      }}
      data-state={
        data.versions.length
          ? "result"
          : data.run.status === "running"
            ? "running"
            : data.run.status === "failed"
              ? "failed"
              : "draft"
      }
      data-kind={data.subject ? "edit" : "origin"}
      data-selected={selected || undefined}
      data-blocked={nodeIsBlocked(data) || undefined}
      data-wire-highlighted={data.wireHighlighted || undefined}
      className="design-card w-[19rem] rounded-[var(--radius-surface)] bg-white text-foreground"
    >
      <NodeHandle data={data} id={id} role="subject" type="source" />
      <NodeHandle data={data} id={id} role="connect" type="source" />
      {!data.subject ? (
        <NodeHandle data={data} id={id} role="subject" type="target" fallback />
      ) : null}
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3 py-1.5">
        <div className="min-w-0 flex-1">{title}</div>
        {menu}
      </div>
      <div className="node-body">{children}</div>
    </div>
  );
}
