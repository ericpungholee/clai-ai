"use client";

import { useEffect, useRef, useState } from "react";
import { getCollapsePreview, type CollapsePreview } from "@/lib/graph";

export function CollapseDialog({
  projectId,
  versionId,
  onClose,
  onRun,
}: {
  projectId: string;
  versionId: string;
  onClose: () => void;
  onRun: (rootVersionId: string, instruction: string) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [preview, setPreview] = useState<CollapsePreview | null>(null);
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    dialog.current?.showModal();
    let alive = true;
    getCollapsePreview(projectId, versionId)
      .then((result) => {
        if (!alive) return;
        setPreview(result);
        if (result.status === "ready") setInstruction(result.instruction);
      })
      .catch((error) => {
        if (alive)
          setError(error instanceof Error ? error.message : "Preview failed");
      });
    return () => {
      alive = false;
    };
  }, [projectId, versionId]);
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      className="m-auto w-[620px] rounded-xl p-6 backdrop:bg-black/50"
    >
      <header className="flex justify-between gap-4">
        <h2 className="text-lg font-semibold">Collapse edit chain</h2>
        <button onClick={onClose}>Close · Esc</button>
      </header>
      <p className="my-3 text-sm text-neutral-600">
        A new node applies these instructions to the original input image in one
        edit. The old chain stays intact; compare both when it finishes. This is
        a new paid image run.
      </p>
      {preview?.status === "ready" ? (
        <>
          <label
            className="text-xs text-neutral-500"
            htmlFor="collapse-instruction"
          >
            {preview.steps} edits → one editable instruction
          </label>
          <textarea
            id="collapse-instruction"
            className="mt-2 h-64 w-full rounded border p-3 text-sm"
            maxLength={8000}
            value={instruction}
            disabled={busy}
            onChange={(event) => setInstruction(event.target.value)}
          />
          <button
            disabled={busy || !instruction.trim()}
            className="mt-4 rounded bg-neutral-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onRun(preview.root_version_id, instruction);
              } catch (error) {
                setError(
                  error instanceof Error ? error.message : "Collapse failed",
                );
                setBusy(false);
              }
            }}
          >
            {busy
              ? "Applying one edit to the root…"
              : "Run collapse against root"}
          </button>
        </>
      ) : preview ? (
        <p className="rounded bg-amber-50 p-3 text-sm">{preview.reason}</p>
      ) : !error ? (
        <p>Reading this chain…</p>
      ) : null}
      {error ? (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}
    </dialog>
  );
}
