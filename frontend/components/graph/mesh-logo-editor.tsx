"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import { selectMask, type Version } from "@/lib/graph";
import { cropLogo, readLogoSource, type MeshDecal } from "@/lib/mesh-decals";

export function MeshLogoEditor({
  projectId,
  version,
  decal,
  placing,
  onChange,
  onPlacing,
}: {
  projectId: string;
  version: Version;
  decal: MeshDecal | null;
  placing: boolean;
  onChange: (decal: MeshDecal | null) => void;
  onPlacing: (placing: boolean) => void;
}) {
  const sourceCanvas = useRef<HTMLCanvasElement>(null);
  const [sourceReady, setSourceReady] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selecting = useRef(false);
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    const abort = new AbortController();
    readLogoSource(version.artifact_url, abort.signal)
      .then((source) => {
        if (abort.signal.aborted || !sourceCanvas.current) return;
        sourceCanvas.current.width = source.width;
        sourceCanvas.current.height = source.height;
        sourceCanvas.current.getContext("2d")!.drawImage(source, 0, 0);
        setSourceReady(true);
      })
      .catch(() => {
        if (!abort.signal.aborted)
          setSourceError(
            "The source image cannot be read for cropping. Check the storage host’s CORS policy and try reopening this view. No selection was charged.",
          );
      });
    return () => {
      alive.current = false;
      abort.abort();
    };
  }, [version.artifact_url]);

  async function select(event: MouseEvent<HTMLButtonElement>) {
    const source = sourceCanvas.current;
    if (!source || !sourceReady || selecting.current) return;
    const rect = source.getBoundingClientRect();
    // Keyboard activation selects the center; pointer coordinates use the rendered image bounds.
    const x =
      event.detail === 0
        ? source.width / 2
        : ((event.clientX - rect.left) / rect.width) * source.width;
    const y =
      event.detail === 0
        ? source.height / 2
        : ((event.clientY - rect.top) / rect.height) * source.height;
    if (x < 0 || y < 0 || x >= source.width || y >= source.height) return;
    selecting.current = true;
    setBusy(true);
    setError(null);
    try {
      const mask = await selectMask(projectId, version.id, "logo", [
        { x: Math.floor(x), y: Math.floor(y), label: 1 },
      ]);
      if (!alive.current) return;
      if (!mask)
        throw new Error("Nothing matched. Click another part of the logo.");
      if (mask.subject_version_id !== version.id)
        throw new Error("The selection belongs to another image. Try again.");
      const crop = cropLogo(source, mask);
      onChange({ crop, placement: null, size: 0.25, rotation: 0 });
      onPlacing(true);
    } catch (error) {
      if (alive.current)
        setError(
          error instanceof Error
            ? error.message
            : "The logo could not be selected. Try again.",
        );
    } finally {
      selecting.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <aside
      aria-label="Source logo"
      className="w-full shrink-0 space-y-3 overflow-y-auto border-b border-neutral-200 bg-white p-3 md:h-full md:w-72 md:border-b-0 md:border-r"
    >
      <button
        type="button"
        aria-label="Select logo in source image"
        title="Click to select a logo · ~$0.005 per selection"
        disabled={!sourceReady || busy}
        onClick={(event) => void select(event)}
        className="block w-full cursor-crosshair overflow-hidden rounded border border-neutral-200 disabled:cursor-wait"
      >
        <canvas
          ref={sourceCanvas}
          role="img"
          aria-label="Original 2D image used for this 3D view"
          className="block h-auto w-full"
        />
      </button>
      {!sourceReady && !sourceError ? (
        <p role="status" className="text-xs">
          Loading source image…
        </p>
      ) : null}
      {busy ? (
        <p role="status" className="text-xs">
          Isolating logo…
        </p>
      ) : null}
      {sourceError || error ? (
        <p role="alert" className="text-xs text-red-700">
          {sourceError || error}
        </p>
      ) : null}
      {decal ? (
        <>
          <figure className="rounded border border-neutral-200 bg-[repeating-conic-gradient(#e5e5e5_0%_25%,white_0%_50%)] bg-[length:16px_16px] p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={decal.crop.dataUrl}
              alt="Isolated logo crop"
              className="mx-auto max-h-28 max-w-full object-contain"
            />
          </figure>
          <button
            type="button"
            disabled={busy}
            aria-pressed={placing}
            onClick={() => onPlacing(!placing)}
            className="w-full rounded bg-neutral-900 px-3 py-2 text-sm text-white disabled:opacity-50"
          >
            {placing
              ? "Cancel placement"
              : decal.placement
                ? "Move logo"
                : "Place logo"}
          </button>
          <p role="status" className="sr-only">
            {placing
              ? "Click a point on the mesh. Drag to orbit and inspect the surface."
              : decal.placement
                ? "Logo placed. Drag the model to inspect it."
                : "Choose Place logo, then click the mesh."}
          </p>
          <label className="block text-xs">
            Logo size <output>{Math.round(decal.size * 100)}%</output>
            <input
              aria-label="Logo size"
              type="range"
              min="2"
              max="100"
              step="1"
              value={Math.round(decal.size * 100)}
              disabled={busy}
              onChange={(event) =>
                onChange({ ...decal, size: Number(event.target.value) / 100 })
              }
              className="mt-2 w-full"
            />
          </label>
          <label className="block text-xs">
            Logo rotation <output>{decal.rotation}°</output>
            <input
              aria-label="Logo rotation"
              type="range"
              min="-180"
              max="180"
              step="1"
              value={decal.rotation}
              disabled={busy}
              onChange={(event) =>
                onChange({ ...decal, rotation: Number(event.target.value) })
              }
              className="mt-2 w-full"
            />
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              onChange(null);
              onPlacing(false);
            }}
            className="text-xs underline"
          >
            Remove logo
          </button>
        </>
      ) : null}
    </aside>
  );
}
