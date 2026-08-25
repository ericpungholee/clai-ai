import type { NodeProps } from "@xyflow/react";
import { memo } from "react";

import type { WorkspaceNode } from "@/lib/graph";

import { NodeFrame } from "./node-frame";

export const ModelNode = memo(function ModelNode({
  selected,
}: NodeProps<WorkspaceNode>) {
  return (
    <NodeFrame selected={selected} title="3D">
      <p className="py-5 text-center text-sm text-muted">No model yet</p>
    </NodeFrame>
  );
});
