import type { NodeProps } from "@xyflow/react";
import { memo } from "react";

import type { WorkspaceNode } from "@/lib/graph";

import { useDesignNodeActions } from "./design-node-actions";
import { NodeFrame } from "./node-frame";
import { PromptEditor } from "./prompt-editor";
import { VersionStrip } from "./version-strip";

export const DesignNode = memo(function DesignNode({
  id,
  data,
  selected,
}: NodeProps<WorkspaceNode>) {
  const actions = useDesignNodeActions();
  const activeVersion = data.versions.find(
    (version) => version.id === data.activeVersionId,
  );
  const staleMask =
    data.mask !== null &&
    data.mask.subject_version_id !== data.subject?.versionId;
  const brokenConnect = data.connects.some((ref) => ref.state !== "ready");
  const fullMask =
    data.mask !== null &&
    data.mask.rle === `1 ${data.mask.width * data.mask.height}`;
  const unsupportedMask =
    data.mask !== null && !fullMask && data.connects.length > 0;
  const canRun =
    !brokenConnect &&
    !unsupportedMask &&
    data.prompt.trim().length > 0 &&
    data.runState !== "running" &&
    !staleMask;

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
        <button
          className="nodrag block w-full cursor-zoom-in"
          aria-label="Inspect active image"
          onClick={() => actions.viewVersions([activeVersion.id])}
        >
          <ArtifactImage
            alt={`${data.title} active version`}
            className="aspect-[4/3] w-full rounded-lg bg-neutral-100 object-cover"
            src={activeVersion.artifact_url}
          />
        </button>
      ) : (
        <div className="flex aspect-[4/3] items-center justify-center rounded-lg border border-dashed border-neutral-300 bg-neutral-50 px-5 text-center text-xs text-neutral-400">
          Run this node to create an image
        </div>
      )}
      {activeVersion ? (
        <div className="mt-2 flex justify-between gap-2 text-xs">
          <button
            className="nodrag rounded bg-sky-50 px-2 py-1 font-medium text-sky-800"
            onClick={() => actions.branchVersion(id, activeVersion.id)}
          >
            + Branch this image
          </button>
          <span className="self-center text-neutral-400">
            {activeVersion.edit_depth} edit hops
          </span>
        </div>
      ) : null}
      {activeVersion && activeVersion.edit_depth >= 5 ? (
        <div className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-900">
          Long edit chains can lose identity. Try the same instructions against
          the root.
          <button
            className="nodrag mt-1 block underline"
            onClick={() => actions.collapseVersion(activeVersion.id)}
          >
            Collapse chain and compare…
          </button>
        </div>
      ) : activeVersion && activeVersion.edit_depth >= 2 ? (
        <button
          className="nodrag mt-2 text-[11px] text-neutral-500 underline"
          onClick={() => actions.collapseVersion(activeVersion.id)}
        >
          Collapse chain…
        </button>
      ) : null}
      {activeVersion?.masked_outside_change != null ? (
        <p className="mt-2 text-[11px] text-neutral-500">
          Outside the mask + 3px feather:{" "}
          {activeVersion.masked_outside_change === 0
            ? "pixels preserved exactly"
            : `${(activeVersion.masked_outside_change * 100).toFixed(3)}% mean pixel change`}
          . This measures preservation, not edit quality.
        </p>
      ) : null}

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

      <PromptEditor
        document={data.document}
        connects={data.connects}
        candidates={actions.candidates(id)}
        onChange={(document) => actions.updateDocument(id, document)}
        onHover={actions.hoverNode}
        onJump={actions.jumpNode}
        onRun={() => actions.runNode(id)}
        placeholder={
          data.subject
            ? "Describe one change — e.g. ‘square the base’, ‘brushed aluminium body’"
            : "A compact desk lamp with a folded aluminium shade and a round walnut foot"
        }
      />
      {brokenConnect ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          A connect source is deleted or has no image. Remove the chip or run
          its source first.
        </p>
      ) : null}
      {unsupportedMask ? (
        <p role="alert" className="mt-2 text-xs text-amber-700">
          Clear the mask or remove connect chips: FLUX Fill cannot consume
          reference images.
        </p>
      ) : null}

      {data.versions.length > 0 ? (
        <VersionStrip
          nodeId={id}
          versions={data.versions}
          activeId={data.activeVersionId}
        />
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
