"use client";
import type { Version } from "@/lib/graph";
import { useDesignNodeActions } from "./design-node-actions";
export function VersionStrip({
  nodeId,
  versions,
  activeId,
}: {
  nodeId: string;
  versions: Version[];
  activeId: string | null;
}) {
  const actions = useDesignNodeActions();
  return (
    <div>
      <div
        className="nodrag nowheel flex gap-2 overflow-x-auto"
        aria-label="Legacy images"
      >
        {versions.map((image, index) => (
          <button
            key={image.id}
            aria-label={`Select image ${index + 1}`}
            aria-pressed={image.id === activeId}
            onClick={() => actions.selectVersion(nodeId, image.id)}
            className="w-12 shrink-0 rounded border aria-pressed:border-orange-500"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={image.artifact_url}
              alt={`Image ${index + 1}`}
              className="h-9 object-contain"
            />
          </button>
        ))}
      </div>
    </div>
  );
}
