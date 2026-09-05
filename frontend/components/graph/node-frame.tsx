import { Handle, Position, useConnection } from "@xyflow/react";
import type { ReactNode } from "react";
import type { DesignNodeData } from "@/lib/graph";

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
  const connection = useConnection();
  const fromId = connection.fromNode?.id;
  const sourceRole = connection.fromHandle?.id;
  return (
    <div
      data-kind={data.subject ? "edit" : "origin"}
      className={`design-card w-[19rem] rounded-[var(--radius-surface)] border bg-white text-foreground shadow-sm ${selected ? "border-blue-500" : "border-neutral-300"}`}
    >
      {(["subject", "connect"] as const).flatMap((role) =>
        (["target", "source"] as const).map((type) => {
          const available =
            type === "source"
              ? role === "connect" || !!data.activeVersionId
              : role === "subject" || data.connects.length < 2;
          const validDrag =
            connection.inProgress &&
            type === "target" &&
            fromId !== id &&
            sourceRole === role &&
            available &&
            !data.connects.some(
              (ref) => role === "connect" && ref.nodeId === fromId,
            );
          return (
            <Handle
              key={`${type}-${role}`}
              id={role}
              type={type}
              position={type === "target" ? Position.Left : Position.Right}
              className={`wire-handle wire-${role === "connect" ? "reference" : "subject"} ${available ? "available" : ""} ${validDrag ? "valid-drop" : ""}`}
              data-dragging={connection.inProgress || undefined}
              aria-label={`${type === "source" ? "Start" : "Connect"} ${role === "subject" ? "subject" : "reference"}`}
              title={`${type === "source" ? "Start" : "Connect"} ${role === "subject" ? "subject" : "reference"}`}
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
        }),
      )}
      <div className="flex items-center gap-2 border-b border-neutral-100 px-3 py-1.5">
        <div className="min-w-0 flex-1">{title}</div>
        {menu}
      </div>
      <div className="space-y-2 p-2.5">{children}</div>
    </div>
  );
}
