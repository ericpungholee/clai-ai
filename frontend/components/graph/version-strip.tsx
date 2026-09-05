"use client";
import { useEffect, useRef, useState } from "react";
import type { Version } from "@/lib/graph";
import { useDesignNodeActions } from "./design-node-actions";
import { OverflowMenu } from "./overflow-menu";

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
  const hiddenCount = versions.filter((version) => version.hidden).length;
  return (
    <div
      ref={strip}
      className="nodrag nowheel flex items-center gap-2 overflow-x-auto p-0.5"
      aria-label="Versions"
    >
      {versions.map((version, index) =>
        !version.hidden || showHidden ? (
          <div
            key={version.id}
            className={`version-thumbnail relative w-12 shrink-0 ${version.hidden ? "opacity-50" : ""}`}
          >
            <button
              aria-label={`Select version ${index + 1}`}
              aria-pressed={version.id === activeId}
              onClick={() => actions.selectVersion(nodeId, version.id)}
              className={`block w-full overflow-hidden rounded border ${version.id === activeId ? "border-blue-600 ring-1 ring-blue-600" : "border-neutral-200"}`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                alt=""
                src={version.artifact_url}
                loading="lazy"
                draggable={false}
                className="h-9 w-full object-cover"
              />
              <span className="block bg-neutral-50 text-[9px] text-neutral-500">
                v{index + 1}
              </span>
            </button>
            <OverflowMenu
              label={`Version ${index + 1} actions`}
              className="thumbnail-menu absolute right-0 top-0 rounded bg-white/95"
            >
              <button
                aria-label={`Branch from version ${index + 1}`}
                onClick={() => actions.branchVersion(nodeId, version.id)}
              >
                Branch
              </button>
              <button
                aria-label={`${version.hidden ? "Restore" : "Hide"} version ${index + 1}`}
                onClick={() => actions.hideVersion(version.id, !version.hidden)}
              >
                {version.hidden ? "Restore" : "Hide"}
              </button>
              {activeId && activeId !== version.id ? (
                <button
                  aria-label={`Compare version ${index + 1}`}
                  onClick={() => actions.viewVersions([activeId, version.id])}
                >
                  Compare
                </button>
              ) : null}
              {version.branch_node_ids.some((id) => names.has(id)) ? (
                <div className="border-t pt-1">
                  <p className="px-2 text-[10px] text-neutral-500">
                    Used by{" "}
                    {
                      version.branch_node_ids.filter((id) => names.has(id))
                        .length
                    }{" "}
                    {version.branch_node_ids.filter((id) => names.has(id))
                      .length === 1
                      ? "node"
                      : "nodes"}
                  </p>
                  {version.branch_node_ids
                    .filter((id) => names.has(id))
                    .map((id) => (
                      <button
                        key={id}
                        aria-label={`Find ${names.get(id)}`}
                        title={names.get(id)}
                        onClick={() => actions.jumpNode(id)}
                      >
                        {names.get(id)}
                      </button>
                    ))}
                </div>
              ) : null}
            </OverflowMenu>
          </div>
        ) : null,
      )}
      {hiddenCount ? (
        <button
          aria-label={showHidden ? "Hide retained" : "Show retained"}
          title={showHidden ? "Hide retained" : "Show retained"}
          aria-expanded={showHidden}
          onClick={() => setShowHidden(!showHidden)}
          className="shrink-0 rounded border border-neutral-200 px-2 py-1 text-[10px] text-neutral-500"
        >
          {showHidden ? "−" : "+"}
          {hiddenCount}
        </button>
      ) : null}
    </div>
  );
}
