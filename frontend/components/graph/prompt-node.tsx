import type { NodeProps } from "@xyflow/react";
import { memo } from "react";

import type { WorkspaceNode } from "@/lib/graph";

import { NodeFrame } from "./node-frame";
import { useUpdatePromptText } from "./prompt-node-actions";

export const PromptNode = memo(function PromptNode({
  data,
  id,
  selected,
}: NodeProps<WorkspaceNode>) {
  const updatePromptText = useUpdatePromptText();
  const text = typeof data.text === "string" ? data.text : "";

  return (
    <NodeFrame selected={selected} title="Prompt">
      <textarea
        aria-label="Prompt text"
        className="nodrag nopan nowheel block min-h-24 w-full resize-none bg-transparent text-sm leading-5 text-foreground outline-none placeholder:text-neutral-400"
        onChange={(event) => updatePromptText(id, event.target.value)}
        onKeyDown={(event) => event.stopPropagation()}
        placeholder="Describe a product concept"
        spellCheck
        value={text}
      />
    </NodeFrame>
  );
});
