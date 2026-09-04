import type { NodeProps } from "@xyflow/react";
import { memo } from "react";

import type { WorkspaceNode } from "@/lib/graph";

import { useDesignNodeActions } from "./design-node-actions";
import { NodeFrame } from "./node-frame";

export const DesignNode = memo(function DesignNode({
  id,
  data,
  selected,
}: NodeProps<WorkspaceNode>) {
  const actions = useDesignNodeActions();
  const activeVersion =
    data.versions.find((version) => version.id === data.activeVersionId) ??
    data.versions.at(-1);
  const staleMask =
    data.mask !== null &&
    data.mask.subject_version_id !== data.subject?.versionId;
  const canRun =
    data.prompt.trim().length > 0 && data.runState !== "running" && !staleMask;

  return (
    <NodeFrame
      selected={selected}
      title={
        <input
          aria-label="Node title"
          className="nodrag w-full bg-transparent text-xs font-semibold text-neutral-700 outline-none focus:text-neutral-950"
          maxLength={120}
          onChange={(event) => actions.updateTitle(id, event.target.value)}
          onKeyDown={(event) => event.stopPropagation()}
          value={data.title}
        />
      }
    >
      {activeVersion ? (
        <ArtifactImage
          alt={`${data.title} active version`}
          className="aspect-[4/3] w-full rounded-lg bg-neutral-100 object-cover"
          src={activeVersion.artifact_url}
        />
      ) : (
        <div className="flex aspect-[4/3] items-center justify-center rounded-lg border border-dashed border-neutral-300 bg-neutral-50 px-5 text-center text-xs text-neutral-400">
          Run this node to create an image
        </div>
      )}

      {data.subject ? (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 p-2">
          <ArtifactImage
            alt={`${data.subject.nodeTitle} pinned subject`}
            className="h-10 w-10 shrink-0 rounded-md object-cover"
            src={data.subject.artifactUrl}
          />
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-sky-700">
              Subject
            </p>
            <p className="truncate text-xs text-neutral-700">
              {data.subject.nodeTitle}
            </p>
          </div>
        </div>
      ) : null}

      {data.subject ? (
        <button
          className="nodrag mt-2 w-full rounded-md border border-orange-200 bg-orange-50 py-1.5 text-xs text-orange-900"
          onClick={() => actions.editMask(id)}
        >
          {data.mask ? "Edit mask" : "Select an area to edit"}
        </button>
      ) : null}
      {staleMask ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          This mask belongs to a different subject version. Reopen the mask
          editor before running.
        </p>
      ) : null}

      <textarea
        aria-label="Design prompt"
        className="nodrag nowheel mt-3 min-h-20 w-full resize-none rounded-lg border border-neutral-200 bg-white px-2.5 py-2 text-sm leading-5 text-foreground outline-none placeholder:text-neutral-400 focus:border-sky-400"
        onChange={(event) => actions.updatePrompt(id, event.target.value)}
        onKeyDown={(event) => event.stopPropagation()}
        placeholder={
          data.subject
            ? "Describe one change — e.g. ‘square the base’, ‘brushed aluminium body’"
            : "A compact desk lamp with a folded aluminium shade and a round walnut foot"
        }
        spellCheck
        value={data.prompt}
      />

      {data.versions.length > 0 ? (
        <div className="mt-3">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-neutral-400">
            Versions
          </p>
          <div className="nodrag nowheel flex gap-1.5 overflow-x-auto pb-1">
            {data.versions.map((version, index) => (
              <div className="group/version relative shrink-0" key={version.id}>
                <button
                  aria-label={`Select version ${index + 1}`}
                  className={`block h-11 w-11 overflow-hidden rounded-md border-2 ${
                    version.id === activeVersion?.id
                      ? "border-sky-500"
                      : "border-transparent"
                  }`}
                  onClick={() => actions.selectVersion(id, version.id)}
                  title={`Version ${index + 1}`}
                  type="button"
                >
                  <ArtifactImage
                    alt=""
                    className="h-full w-full object-cover"
                    src={version.artifact_url}
                  />
                </button>
                <button
                  aria-label={`Branch from version ${index + 1}`}
                  className="absolute -right-1 -top-1 hidden h-4 w-4 items-center justify-center rounded-full bg-neutral-900 text-[10px] leading-none text-white group-hover/version:flex focus:flex"
                  onClick={() => actions.branchVersion(id, version.id)}
                  title={`Branch from version ${index + 1}`}
                  type="button"
                >
                  +
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex items-center justify-between gap-2">
        {!data.subject ? (
          <label className="nodrag flex items-center gap-1.5 text-[11px] text-neutral-600">
            <input
              checked={data.settings.whiteBackground}
              className="h-3.5 w-3.5 accent-sky-600"
              onChange={(event) =>
                actions.updateWhiteBackground(id, event.target.checked)
              }
              type="checkbox"
            />
            White background
          </label>
        ) : (
          <span />
        )}
        <button
          className="nodrag rounded-md bg-neutral-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
          disabled={!canRun}
          onClick={() => actions.runNode(id)}
          type="button"
        >
          {data.runState === "running" ? "Running…" : "Run"}
        </button>
      </div>
      {data.runError ? (
        <p className="mt-2 text-xs text-red-600">{data.runError}</p>
      ) : null}
    </NodeFrame>
  );
});

function ArtifactImage({
  alt,
  className,
  src,
}: {
  alt: string;
  className: string;
  src: string;
}) {
  // Artifact hosts are runtime-configured, so a static next/image allowlist is unsafe.
  // eslint-disable-next-line @next/next/no-img-element
  return <img alt={alt} className={className} draggable={false} src={src} />;
}
