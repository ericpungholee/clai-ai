"use client";

import { useEffect, useRef, useState } from "react";
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
  const [showHidden, setShowHidden] = useState(false);
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    strip.current
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [activeId]);
  const names = new Map(
    actions.candidates(nodeId).map((node) => [node.id, node.title]),
  );
  return (
    <section className="mt-3">
      <div className="mb-2 flex items-center justify-between text-[10px] text-neutral-500">
        <span>
          Versions · {versions.filter((version) => !version.hidden).length}{" "}
          visible
        </span>
        {versions.some((version) => version.hidden) ? (
          <button className="nodrag" onClick={() => setShowHidden(!showHidden)}>
            {showHidden ? "Hide retained" : "Show retained"}
          </button>
        ) : null}
      </div>
      <div
        ref={strip}
        className="nodrag nowheel flex gap-2 overflow-x-auto pb-2"
      >
        {versions.map((version, index) =>
          !version.hidden || showHidden ? (
            <div
              key={version.id}
              className={`w-16 shrink-0 ${version.hidden ? "opacity-50" : ""}`}
            >
              <button
                aria-label={`Select version ${index + 1}`}
                aria-pressed={version.id === activeId}
                onClick={() => actions.selectVersion(nodeId, version.id)}
                className={`block w-full overflow-hidden rounded-md border-2 ${version.id === activeId ? "border-sky-600 ring-2 ring-sky-200" : "border-neutral-200"}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt=""
                  src={version.artifact_url}
                  loading="lazy"
                  draggable={false}
                  className="h-12 w-full object-cover"
                />
                <span
                  className={`block text-[10px] ${version.id === activeId ? "bg-sky-600 text-white" : "bg-neutral-50"}`}
                >
                  v{index + 1}
                  {version.id === activeId ? " · active" : ""}
                </span>
              </button>
              <div className="mt-1 flex justify-between text-[10px] text-neutral-500">
                <button
                  aria-label={`Branch from version ${index + 1}`}
                  title="New direction from this exact image"
                  onClick={() => actions.branchVersion(nodeId, version.id)}
                >
                  + Branch
                </button>
                <button
                  aria-label={`${version.hidden ? "Restore" : "Hide"} version ${index + 1}`}
                  title="Hide from strip; keep artifact and history"
                  onClick={() =>
                    actions.hideVersion(version.id, !version.hidden)
                  }
                >
                  {version.hidden ? "↶" : "−"}
                </button>
              </div>
              {version.branch_node_ids.length > 0 ? (
                <details className="mt-1 text-[10px] text-violet-700">
                  <summary className="cursor-pointer">
                    ↗ {version.branch_node_ids.length} branches
                  </summary>
                  {version.branch_node_ids.map((id) => (
                    <button
                      key={id}
                      title={names.get(id)}
                      className="block w-full truncate text-left"
                      onClick={() => actions.jumpNode(id)}
                    >
                      {names.get(id) ?? "Concept"}
                    </button>
                  ))}
                </details>
              ) : null}
            </div>
          ) : null,
        )}
      </div>
      <div className="mt-1 flex items-center gap-2 text-[11px] text-neutral-500">
        <span>Compare active to</span>
        <select
          aria-label="Compare active version to"
          className="nodrag min-w-0 flex-1 rounded border p-1"
          value=""
          disabled={!activeId}
          onChange={(event) => {
            if (activeId && event.target.value)
              actions.viewVersions([activeId, event.target.value]);
          }}
        >
          <option value="">Choose version…</option>
          {versions
            .filter((version) => version.id !== activeId)
            .map((version) => (
              <option key={version.id} value={version.id}>
                v{versions.indexOf(version) + 1}
                {version.hidden ? " (retained)" : ""}
              </option>
            ))}
        </select>
      </div>
    </section>
  );
}
