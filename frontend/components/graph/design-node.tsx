import { DownloadButton } from "./download-button";
import type { NodeProps } from "@xyflow/react";
import { memo, useState } from "react";
import {
  runBlockingReason,
  type WorkspaceNode,
  type DesignNodeData,
} from "@/lib/graph";
import { useDesignNodeActions } from "./design-node-actions";
import { NodeFrame, NodeHandle } from "./node-frame";
import { PromptEditor } from "./prompt-editor";
import { VersionStrip } from "./version-strip";
import { RunProgress } from "./run-progress";
import { SaveStatus } from "./save-status";
import { Icon, IconButton } from "./icon";
import { OverflowMenu } from "./overflow-menu";
import { MaskOutline } from "./mask-outline";

export const DesignNode = memo(function DesignNode({
  id,
  data,
  selected,
}: NodeProps<WorkspaceNode>) {
  const actions = useDesignNodeActions();
  const activeVersion =
    data.versions.find((image) => image.id === data.activeVersionId) ??
    data.versions[0];
  const result = data.versions.length > 0;
  const running = data.run.status === "running";
  const locked = result || running;
  const hasSubject = !!data.subject;
  const meshPreview =
    data.meshPreview?.versionId === activeVersion?.id ? data.meshPreview : null;
  const showMesh = !!meshPreview && data.previewMode !== "image";
  const preview = showMesh ? meshPreview.url : activeVersion?.artifact_url;
  const blocked = runBlockingReason(data);
  const visibleWarning = blocked === "Enter a prompt." ? null : blocked;
  const failed = data.run.status === "failed";
  const warning =
    !result && !running
      ? (visibleWarning ??
        (failed
          ? data.run.status === "failed"
            ? data.run.message
            : "Run failed — retry."
          : null) ??
        (data.subject?.deleted
          ? "Source node deleted. This image is retained and still usable."
          : null))
      : null;
  const run = () => {
    if (!blocked) actions.runNode(id);
  };
  const broken = data.connects.find((ref) => ref.state !== "ready");
  const stale =
    data.mask && data.mask.subject_version_id !== data.subject?.versionId;
  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      title={
        <input
          aria-label="Node title"
          title={data.title}
          placeholder="Name this node"
          className="node-title nodrag w-full truncate bg-transparent text-xs font-semibold text-neutral-700 outline-none"
          maxLength={120}
          onChange={(e) => actions.updateTitle(id, e.target.value)}
          onKeyDown={(e) => e.stopPropagation()}
          value={data.title}
        />
      }
      menu={
        <>
          <SaveStatus state={data.draftError ? "failed" : data.saveState} />
          <OverflowMenu label="Node actions">
            {!result && !running ? (
              <button onClick={() => actions.duplicateNode(id)}>
                Duplicate draft
              </button>
            ) : null}
            <button onClick={() => actions.deleteNode(id)}>Delete node</button>
          </OverflowMenu>
        </>
      }
    >
      {preview ? (
        <div className="image-preview group relative overflow-hidden rounded-md bg-white">
          <button
            className="nodrag block w-full cursor-zoom-in"
            aria-label="Inspect result"
            onClick={() =>
              actions.viewVersions([activeVersion!.id])
            }
          >
            <ArtifactImage
              alt={`${data.title} preview`}
              className="aspect-[4/3] w-full object-contain"
              src={preview}
            />
          </button>
          {data.mask && !showMesh && !stale ? (
            <MaskOutline mask={data.mask} />
          ) : null}
          {meshPreview ? (
            <div
              role="group"
              aria-label="Image view"
              className="absolute right-2 top-2 flex rounded bg-white"
            >
              <IconButton
                icon="image"
                label="2D image"
                aria-pressed={!showMesh}
                onClick={() => actions.viewImage(id)}
              />
              <IconButton
                icon="mesh"
                label="3D preview"
                aria-pressed={showMesh}
                onClick={() => actions.showMesh(id)}
              />
            </div>
          ) : null}
          {activeVersion && activeVersion.edit_depth >= 2 ? (
            <button
              aria-label="Collapse chain"
              className="nodrag absolute left-2 top-2 rounded bg-white px-1.5 py-0.5 text-[10px]"
              onClick={() => actions.collapseVersion(activeVersion.id)}
            >
              {activeVersion.edit_depth} edits
            </button>
          ) : null}
          <div
            className="preview-toolbar absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-white px-1.5 py-1"
            role="toolbar"
            aria-label="Image actions"
          >
            {activeVersion ? <DownloadButton url={activeVersion.artifact_url} name={`${data.title}-${activeVersion.id}`} /> : null}
            {activeVersion ? (
              <IconButton
                icon="mesh"
                label="3D"
                onClick={() => actions.viewMesh(activeVersion.id)}
              />
            ) : null}
          </div>
        </div>
      ) : null}
      <SubjectRow id={id} data={data} locked={locked} />
      {!result ? (
        <div
          className="nowheel h-16 overflow-y-auto text-[10px] text-red-700"
          role={warning ? "alert" : undefined}
        >
          {warning}
          {broken ? (
            <button
              className="nodrag ml-1 underline"
              onClick={() =>
                broken.state === "empty"
                  ? actions.jumpNode(broken.nodeId)
                  : actions.updateDocument(
                      id,
                      data.document.filter(
                        (part) =>
                          part.type !== "connect" ||
                          part.edge_id !== broken.edgeId,
                      ),
                    )
              }
            >
              {broken.state === "empty" ? "Find source" : "Remove reference"}
            </button>
          ) : stale ? (
            <>
              <button
                className="nodrag ml-1 underline"
                onClick={() => actions.editMask(id)}
              >
                Edit area
              </button>
              <button
                className="nodrag ml-1 underline"
                onClick={() => actions.removeMask(id)}
              >
                Remove selection
              </button>
            </>
          ) : data.mask && data.connects.length ? (
            <button
              className="nodrag ml-1 underline"
              onClick={() => actions.removeMask(id)}
            >
              Remove selection
            </button>
          ) : data.draftError && !data.remoteDeleted ? (
            <>
              <button
                className="nodrag ml-1 underline"
                onClick={() => actions.resolveDraft(id, true)}
              >
                Keep my draft
              </button>
              <button
                className="nodrag ml-1 underline"
                onClick={() => actions.resolveDraft(id, false)}
              >
                Use saved draft
              </button>
            </>
          ) : data.subject?.deleted ? (
            <button
              className="nodrag ml-1 underline"
              onClick={() => actions.disconnectSubject(id)}
            >
              Disconnect input
            </button>
          ) : null}
        </div>
      ) : null}
      {data.mask && !data.prompt.trim() && !locked ? (
        <p className="text-[10px] text-orange-700">
          Area saved. Describe the change, then Run.
        </p>
      ) : null}
      <PromptEditor
        readOnly={locked}
        hasMask={!!data.mask}
        onRemoveMask={() => actions.removeMask(id)}
        referenceHandle={
          <NodeHandle data={data} id={id} role="connect" type="target" />
        }
        document={data.document}
        connects={data.connects}
        hasSubject={hasSubject}
        highlightedWireId={data.highlightedWireId}
        candidates={actions.candidates(id)}
        onChange={(document) => actions.updateDocument(id, document)}
        onHover={actions.hoverWire}
        onJump={actions.jumpNode}
        onRun={run}
        placeholder={
          data.mask
            ? "Describe the change inside the selection…"
            : hasSubject
              ? "Describe a change…"
              : "Describe a design…"
        }
        footer={
          data.run.status === "running" ? (
            <RunProgress run={data.run} />
          ) : !result ? (
            <button
              className="run-button nodrag text-white disabled:bg-neutral-300"
              disabled={!!blocked}
              aria-label={failed ? "Retry" : "Run"}
              title={blocked ?? (failed ? "Retry" : "Run")}
              onClick={run}
            >
              <Icon name="arrowUp" />
            </button>
          ) : null
        }
      />
      {result ? (
        <div className="nodrag flex flex-wrap gap-2">
          <button
            className="w-full rounded bg-neutral-900 px-3 py-2 text-xs font-bold text-white"
            onClick={() => actions.branchVersion(id, activeVersion.id)}
          >
            New node
          </button>
        </div>
      ) : null}
      {data.versions.length > 1 ? (
        <VersionStrip
          nodeId={id}
          versions={data.versions}
          activeId={data.activeVersionId}
        />
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
  // Artifact hosts are runtime-configured.
  // eslint-disable-next-line @next/next/no-img-element
  return <img alt={alt} className={className} draggable={false} src={src} />;
}

function SubjectRow({
  id,
  data,
  locked,
}: {
  id: string;
  data: DesignNodeData;
  locked: boolean;
}) {
  const actions = useDesignNodeActions();
  const [retained, setRetained] = useState(data.subject);
  if (data.subject && retained !== data.subject) setRetained(data.subject);
  const subject = data.subject ?? retained;
  return (
    <div
      className="subject-dock subject-anchor"
      data-connected={!!data.subject}
      aria-hidden={!data.subject}
      inert={!data.subject}
    >
      {data.subject ? (
        <NodeHandle data={data} id={id} role="subject" type="target" />
      ) : null}
      {subject ? (
        <div
          className={`nodrag subject-chip flex h-6 w-full items-center rounded-r pl-6 pr-0.5 ${subject.deleted ? "opacity-50" : ""}`}
          data-highlighted={
            data.highlightedWireId === subject.edgeId || undefined
          }
        >
          {data.connects.length > 0 ? <span className="wire-number subject-number">1</span> : null}
          <button
            className="flex min-w-0 flex-1 items-center gap-2 text-left"
            aria-label={`Inspect ${subject.nodeTitle}`}
            title={
              subject.deleted
                ? "Source node deleted. This image is retained and still usable."
                : subject.nodeTitle
            }
            onClick={() => actions.viewVersions([subject.versionId])}
            onMouseEnter={() => actions.hoverWire(subject.edgeId)}
            onMouseLeave={() => actions.hoverWire(null)}
            onFocus={() => actions.hoverWire(subject.edgeId)}
            onBlur={() => actions.hoverWire(null)}
          >
            <ArtifactImage
              alt=""
              className="h-5 w-5 shrink-0 rounded object-cover"
              src={subject.artifactUrl}
            />
            <span
              className={`truncate text-xs text-neutral-600 ${subject.deleted ? "line-through" : ""}`}
            >
              {subject.nodeTitle}
            </span>
          </button>
          {!locked ? (
            <IconButton
              icon="mask"
              label={data.mask ? "Edit area" : "Select area"}
              onClick={() => actions.editMask(id)}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
