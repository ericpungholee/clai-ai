import type { NodeProps } from "@xyflow/react";
import { memo, useState } from "react";
import {
  runBlockingReason,
  settledRunReason,
  type WorkspaceNode,
  type DesignNodeData,
} from "@/lib/graph";
import { useDesignNodeActions } from "./design-node-actions";
import { NodeFrame, NodeHandle } from "./node-frame";
import { PromptEditor } from "./prompt-editor";
import { VersionStrip } from "./version-strip";
import { RunProgress } from "./run-progress";
import { SaveStatus, saveLabels } from "./save-status";
import { IconButton } from "./icon";
import { OverflowMenu } from "./overflow-menu";
import { MaskOutline } from "./mask-outline";

export const DesignNode = memo(function DesignNode({
  id,
  data,
  selected,
}: NodeProps<WorkspaceNode>) {
  const actions = useDesignNodeActions();
  const activeVersion = data.versions.find(
    (version) => version.id === data.activeVersionId,
  );
  const hasSubject = !!data.subject;
  const meshPreview =
    data.meshPreview?.versionId === activeVersion?.id ? data.meshPreview : null;
  const showMesh = !!meshPreview && data.previewMode !== "image";
  const preview = showMesh
    ? meshPreview.url
    : (activeVersion?.artifact_url ?? data.subject?.artifactUrl);
  const blocked = runBlockingReason(data);
  const settled = settledRunReason(data);
  const failed = data.run.status === "failed";
  const warning = data.draftError
    ? "Draft changed — choose which to keep."
    : blocked && blocked !== "Enter a prompt." && blocked !== "Run in progress."
      ? blocked
      : failed
        ? "Run failed — retry."
        : null;
  const preservation = activeVersion?.masked_outside_change;
  const saveState = data.draftError ? "failed" : data.saveState;
  const run = () => {
    if (!blocked && !settled) actions.runNode(id);
  };

  return (
    <NodeFrame
      id={id}
      data={data}
      selected={selected}
      title={
        <input
          aria-label="Node title"
          title={data.title}
          className="nodrag w-full truncate bg-transparent text-xs font-semibold text-neutral-700 outline-none focus:text-neutral-950"
          maxLength={120}
          onChange={(event) => actions.updateTitle(id, event.target.value)}
          onKeyDown={(event) => event.stopPropagation()}
          value={data.title}
        />
      }
      menu={
        <>
          <SaveStatus state={saveState} />
          <OverflowMenu label="Node actions">
            {!blocked ? (
              <button
                aria-label="Run again"
                onClick={() => actions.runAgain(id)}
              >
                Run again
              </button>
            ) : null}
            <button
              aria-label="Duplicate draft"
              onClick={() => actions.duplicateNode(id)}
            >
              Duplicate draft
            </button>
            {activeVersion && data.versions.length === 1 ? (
              <>
                <button
                  aria-label="Hide version 1"
                  onClick={() => actions.hideVersion(activeVersion.id, true)}
                >
                  Hide
                </button>
                {activeVersion.branch_node_ids.map((branchId) => {
                  const branch = actions
                    .candidates(id)
                    .find((node) => node.id === branchId);
                  return branch ? (
                    <button
                      key={branchId}
                      aria-label={`Find ${branch.title}`}
                      onClick={() => actions.jumpNode(branchId)}
                    >
                      Used by {branch.title}
                    </button>
                  ) : null;
                })}
              </>
            ) : null}
            {!hasSubject && activeVersion && activeVersion.edit_depth >= 2 ? (
              <button
                aria-label="Collapse chain"
                onClick={() => actions.collapseVersion(activeVersion.id)}
              >
                Collapse chain
              </button>
            ) : null}
            <button
              aria-label="Delete node"
              onClick={() => actions.deleteNode(id)}
            >
              Delete node
            </button>
            {data.subject?.deleted ? (
              <button
                aria-label="Disconnect subject"
                onClick={() => actions.disconnectSubject(id)}
              >
                Disconnect subject
              </button>
            ) : null}
            {data.draftError && !data.remoteDeleted ? (
              <>
                <button
                  aria-label="Keep my draft"
                  onClick={() => actions.resolveDraft(id, true)}
                >
                  Keep my draft
                </button>
                <button
                  aria-label="Use saved draft"
                  onClick={() => actions.resolveDraft(id, false)}
                >
                  Use saved draft
                </button>
              </>
            ) : null}
            {data.draftError ? (
              <p className="max-w-64 break-words px-2 py-1 text-xs">
                {data.draftError}
              </p>
            ) : (
              <p className="px-2 py-1 text-xs text-neutral-400">
                {saveLabels[saveState]}
              </p>
            )}
          </OverflowMenu>
        </>
      }
    >
      {preview ? (
        <div className="image-preview group relative overflow-hidden rounded-md bg-neutral-100">
          <button
            className="nodrag block w-full cursor-zoom-in"
            aria-label={
              activeVersion ? "Inspect active image" : "Inspect subject image"
            }
            onClick={() =>
              showMesh && activeVersion
                ? actions.viewMesh(activeVersion.id)
                : actions.viewVersions([
                    activeVersion?.id ?? data.subject!.versionId,
                  ])
            }
          >
            <ArtifactImage
              alt={`${data.title} preview`}
              className="aspect-[4/3] w-full object-contain"
              src={preview}
            />
          </button>
          {data.mask &&
          !showMesh &&
          data.mask.subject_version_id === data.subject?.versionId ? (
            <MaskOutline mask={data.mask} />
          ) : null}
          {meshPreview ? (
            <div
              role="group"
              aria-label="Version view"
              className="absolute right-2 top-2 flex rounded bg-white/95 shadow-sm"
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
          {hasSubject && activeVersion && activeVersion.edit_depth >= 2 ? (
            <button
              aria-label="Collapse chain"
              title={
                activeVersion.edit_depth >= 5
                  ? "Long edit chains can lose identity. Collapse and compare against the root."
                  : "Collapse chain"
              }
              className="nodrag absolute left-2 top-2 rounded bg-white/95 px-1.5 py-0.5 text-[10px] text-neutral-600"
              onClick={() => actions.collapseVersion(activeVersion.id)}
            >
              {activeVersion.edit_depth} edits
            </button>
          ) : null}
          <div
            className="preview-toolbar absolute inset-x-0 bottom-0 flex justify-end gap-1 bg-white/95 px-1.5 py-1"
            role="toolbar"
            aria-label="Image actions"
          >
            <IconButton
              icon="inspect"
              label="Inspect"
              title={
                preservation != null
                  ? `Inspect. Outside the mask and 3px feather: ${preservation === 0 ? "pixels preserved exactly" : `${(preservation * 100).toFixed(3)}% mean pixel change`}. This measures preservation, not edit quality.`
                  : "Inspect"
              }
              onClick={() =>
                actions.viewVersions([
                  activeVersion?.id ?? data.subject!.versionId,
                ])
              }
            />
            {activeVersion ? (
              <IconButton
                icon="branch"
                label="Branch"
                onClick={() => actions.branchVersion(id, activeVersion.id)}
              />
            ) : null}
            {hasSubject ? (
              <IconButton
                icon="mask"
                label={data.mask ? "Edit mask" : "Select area"}
                onClick={() => actions.editMask(id)}
              />
            ) : null}
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
      <SubjectRow id={id} data={data} />
      {warning ? (
        <div
          role="alert"
          title={
            data.draftError ??
            (data.run.status === "failed" ? data.run.message : warning)
          }
          className="flex h-5 items-center gap-1 text-[10px] text-red-700"
        >
          <span className="truncate">{warning}</span>
          {data.draftError && !data.remoteDeleted ? (
            <OverflowMenu label="Resolve draft">
              <button
                aria-label="Keep my draft"
                onClick={() => actions.resolveDraft(id, true)}
              >
                Keep my draft
              </button>
              <button
                aria-label="Use saved draft"
                onClick={() => actions.resolveDraft(id, false)}
              >
                Use saved draft
              </button>
              <p className="max-w-64 break-words px-2 text-xs">
                {data.draftError}
              </p>
            </OverflowMenu>
          ) : failed && !blocked ? (
            <button
              className="nodrag ml-auto underline"
              aria-label="Retry"
              title={blocked ?? "Retry"}
              disabled={!!blocked}
              onClick={() => (settled ? actions.runAgain(id) : run())}
            >
              Retry
            </button>
          ) : null}
        </div>
      ) : null}
      <PromptEditor
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
        placeholder={hasSubject ? "Describe a change…" : "Describe an object…"}
        footer={
          data.run.status === "running" ? (
            <RunProgress run={data.run} />
          ) : (
            <>
              {!hasSubject ? (
                <IconButton
                  icon="background"
                  label="White bg"
                  aria-pressed={data.settings.whiteBackground}
                  onClick={() =>
                    actions.updateWhiteBackground(
                      id,
                      !data.settings.whiteBackground,
                    )
                  }
                />
              ) : null}
              <button
                className="nodrag rounded bg-neutral-900 px-3 py-1 text-xs font-semibold text-white hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-300"
                disabled={!!blocked || !!settled}
                title={blocked ?? settled ?? "Run"}
                onClick={() => (settled ? actions.runAgain(id) : run())}
                type="button"
              >
                Run
              </button>
            </>
          )
        }
      />
      {data.versions.length >= 2 ||
      data.versions.some((version) => version.hidden) ? (
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

function SubjectRow({ id, data }: { id: string; data: DesignNodeData }) {
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
        <button
          className={`nodrag subject-chip flex h-6 w-full items-center gap-2 rounded-r pl-6 pr-1 text-left ${subject.deleted ? "opacity-50" : ""}`}
          aria-label={`Inspect ${subject.nodeTitle}`}
          title={
            subject.deleted
              ? "Source node deleted; pinned image retained"
              : subject.nodeTitle
          }
          onClick={() => actions.viewVersions([subject.versionId])}
          onMouseEnter={() => actions.hoverWire(subject.edgeId)}
          onMouseLeave={() => actions.hoverWire(null)}
          onFocus={() => actions.hoverWire(subject.edgeId)}
          onBlur={() => actions.hoverWire(null)}
          data-highlighted={
            data.highlightedWireId === subject.edgeId || undefined
          }
        >
          <span className="wire-number subject-number">1</span>
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
      ) : null}
    </div>
  );
}
