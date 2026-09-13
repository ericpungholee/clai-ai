"use client";

import { useEffect, useRef, useState } from "react";
import { DownloadButton } from "./download-button";
import { IMAGE_VIEWS, type Version } from "@/lib/graph";

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
      className="m-auto h-[94vh] w-[96vw] max-w-none rounded-xl bg-white p-4 text-neutral-900 backdrop:bg-black/70"
    >
      <header className="mb-3 flex items-center justify-between">
        <p className="text-sm">
          {versions.length === 2 ? "Compare images" : ""}
        </p>
        <button
          onClick={onClose}
          className="rounded border border-neutral-600 px-3 py-1 text-sm"
        >
          Close
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
  const [angle, setAngle] = useState<(typeof IMAGE_VIEWS)[number][0]>("front");
  const imageUrl = version.views?.[angle] ?? version.artifact_url;
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const zoom = (factor: number) =>
    setView((current) => ({
      ...current,
      scale: Math.min(8, Math.max(0.25, current.scale * factor)),
    }));
  return (
    <section className="flex min-h-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2 text-xs text-neutral-600">
        <span>
          {label}
        </span>
        <div className="flex items-center gap-3">
          <button aria-label="Zoom out" onClick={() => zoom(1 / 1.25)}>
            −
          </button>
          <button onClick={() => setView({ scale: 1, x: 0, y: 0 })}>Fit</button>
          <button aria-label="Zoom in" onClick={() => zoom(1.25)}>
            +
          </button>
          <DownloadButton url={imageUrl} name={`${label}-${version.id}-${angle}`} label="Download original" />
        </div>
      </div>
      {version.views?.rear_right && (
        <nav aria-label={`${label} views`} className="flex gap-2 text-xs">
          {IMAGE_VIEWS.map(([item, title]) => (
            <button
              key={item}
              aria-pressed={angle === item}
              className={`rounded border px-3 py-1 capitalize ${angle === item ? "border-neutral-900 bg-neutral-900 text-white" : "border-neutral-300"}`}
              onClick={() => {
                setAngle(item);
                setView({ scale: 1, x: 0, y: 0 });
              }}
            >
              {title}
            </button>
          ))}
        </nav>
      )}
      <div
        className="relative flex min-h-0 flex-1 cursor-grab items-center justify-center overflow-hidden rounded-lg bg-white touch-none active:cursor-grabbing"
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
          src={imageUrl}
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
