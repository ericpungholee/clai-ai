"use client";

import { useEffect, useRef, useState } from "react";
import type { Version } from "@/lib/graph";

export function ImageViewer({
  versions: initialVersions,
  nodeNames = {},
  onClose,
}: {
  versions: Version[];
  nodeNames?: Record<string, string>;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const versions = initialVersions;
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      className="m-auto h-[94vh] w-[96vw] max-w-none rounded-xl bg-neutral-950 p-4 text-white backdrop:bg-black/70"
    >
      <header className="mb-3 flex items-center justify-between">
        <p className="text-sm">
          {versions.length === 2 ? "Compare images" : "Inspect image"} · Scroll
          to zoom, drag to pan
        </p>
        <button
          onClick={onClose}
          className="rounded border border-neutral-600 px-3 py-1 text-sm"
        >
          Close · Esc
        </button>
      </header>
      <div
        className={`grid h-[calc(100%-3rem)] gap-4 ${versions.length === 2 ? "grid-cols-2" : "grid-cols-1"}`}
      >
        {versions.map((version, index) => (
          <ImagePane
            key={`${index}:${version.id}`}
            version={version}
            label={nodeNames[version.node_id] ?? "Image"}
          />
        ))}
      </div>
    </dialog>
  );
}

function ImagePane({ version, label }: { version: Version; label: string }) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const zoom = (factor: number) =>
    setView((current) => ({
      ...current,
      scale: Math.min(8, Math.max(0.25, current.scale * factor)),
    }));
  const download = async () => {
    try {
      const response = await fetch(version.artifact_url);
      if (!response.ok)
        throw new Error("The original file could not be downloaded.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `clai-${version.id}.${blob.type === "image/jpeg" ? "jpg" : blob.type === "image/webp" ? "webp" : "png"}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Download failed");
    }
  };
  return (
    <section className="flex min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-xs text-neutral-300">
        <span>
          {label} · {new Date(version.created_at).toLocaleString()}
        </span>
        <div className="flex items-center gap-3">
          <button aria-label="Zoom out" onClick={() => zoom(1 / 1.25)}>
            −
          </button>
          <button onClick={() => setView({ scale: 1, x: 0, y: 0 })}>Fit</button>
          <button aria-label="Zoom in" onClick={() => zoom(1.25)}>
            +
          </button>
          <button onClick={download}>Download original</button>
        </div>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-red-300">
          {error}
        </p>
      ) : null}
      <div
        className="relative flex min-h-0 flex-1 cursor-grab items-center justify-center overflow-hidden rounded-lg bg-neutral-800 touch-none active:cursor-grabbing"
        onWheel={(event) => {
          event.stopPropagation();
          zoom(event.deltaY < 0 ? 1.1 : 1 / 1.1);
        }}
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, y: event.clientY };
        }}
        onPointerMove={(event) => {
          const last = drag.current;
          if (!last) return;
          setView((current) => ({
            ...current,
            x: current.x + event.clientX - last.x,
            y: current.y + event.clientY - last.y,
          }));
          drag.current = { x: event.clientX, y: event.clientY };
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        {/* The source is the original stored artifact, never a resized thumbnail. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={version.artifact_url}
          alt={label}
          draggable={false}
          className="max-h-full max-w-full object-contain"
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          }}
        />
      </div>
    </section>
  );
}
