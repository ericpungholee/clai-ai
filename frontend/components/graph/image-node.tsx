import type { NodeProps } from "@xyflow/react";
import { memo } from "react";

import type { WorkspaceNode } from "@/lib/graph";

import { NodeFrame } from "./node-frame";

export const ImageNode = memo(function ImageNode({
  selected,
}: NodeProps<WorkspaceNode>) {
  return (
    <NodeFrame selected={selected} title="Image">
      <p className="py-5 text-center text-sm text-muted">No image yet</p>
    </NodeFrame>
  );
});
