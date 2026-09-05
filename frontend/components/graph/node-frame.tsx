import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";

type NodeFrameProps = {
  children: ReactNode;
  selected: boolean;
  title: ReactNode;
};

export function NodeFrame({ children, selected, title }: NodeFrameProps) {
  return (
    <div
      className={`w-[19rem] rounded-[var(--radius-surface)] border bg-white text-foreground shadow-sm ${
        selected ? "border-sky-500" : "border-neutral-300"
      }`}
    >
      <Handle
        className="!h-2.5 !w-2.5 !border-2 !border-white !bg-neutral-400"
        id="subject"
        style={{ top: "35%", background: "#0284c7" }}
        title="Subject · pins this version"
        position={Position.Left}
        type="target"
      />
      <Handle
        className="!h-3 !w-3 !border-2 !border-white !bg-purple-500"
        id="connect"
        position={Position.Left}
        type="target"
        style={{ top: "70%" }}
        title="Connect · follows active image"
      />
      <div className="border-b border-neutral-200 px-3 py-2">{title}</div>
      <div className="p-3">{children}</div>
      <Handle
        className="!h-2.5 !w-2.5 !border-2 !border-white !bg-neutral-400"
        id="source"
        position={Position.Right}
        type="source"
      />
    </div>
  );
}
