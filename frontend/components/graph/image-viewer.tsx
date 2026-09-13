"use client";

import { useEffect, useRef, useState } from "react";
import { DownloadButton } from "./download-button";
import type { ImageAngle, Version } from "@/lib/graph";

const angles = ["front", "right", "back", "left"] as const;
const angleLabels = { front: "Front", right: "Right", back: "Back", left: "Left" };

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
  const [angle, setAngle] = useState<ImageAngle>("front");
  const imageUrl = angle === "front"
    ? version.artifact_url
    : version.views?.[angle]?.image_url;
  const readyCount = 1 + angles.slice(1).filter(
    (key) => version.views?.[key]?.status === "complete",
  ).length;
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
          <DownloadButton
            url={imageUrl ?? version.artifact_url}
            name={`${label}-${version.id}-${angle}`}
            label="Download original"
          />
        </div>
      </div>
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
          src={imageUrl ?? version.artifact_url}
          alt={`${label} — ${angleLabels[angle]} view`}
          draggable={false}
          className="max-h-full max-w-full object-contain"
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          }}
        />
      </div>
      <div className="shrink-0 rounded-lg border border-neutral-200 bg-neutral-50 p-3">
        <p className="mb-2 text-xs text-neutral-600" aria-live="polite">
          Angles for 3D · {readyCount}/4 ready
        </p>
        <div className="grid grid-cols-4 gap-2" aria-label={`${label} image angles`}>
          {angles.map((key) => {
            const artifact = version.views?.[key];
            const url = key === "front"
              ? version.artifact_url
              : artifact?.status === "complete" ? artifact.image_url : null;
            const status = artifact?.status === "failed"
              ? "Unavailable"
              : artifact ? "Generating…" : "Not generated";
            return (
              <button
                key={key}
                disabled={!url}
                aria-label={`Show ${angleLabels[key]} view`}
                aria-pressed={angle === key}
                onClick={() => {
                  setAngle(key);
                  setView({ scale: 1, x: 0, y: 0 });
                }}
                className={`overflow-hidden rounded-md border p-1 text-xs disabled:cursor-default ${angle === key ? "border-neutral-900 bg-white" : "border-neutral-200"}`}
              >
                {url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={url}
                    alt=""
                    className="h-16 w-full rounded object-contain"
                  />
                ) : (
                  <span className="flex h-16 items-center justify-center text-[10px] text-neutral-500">
                    {status}
                  </span>
                )}
                <span className="block pt-1">{angleLabels[key]}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
