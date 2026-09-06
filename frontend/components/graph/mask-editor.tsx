"use client";

import { useEffect, useRef, useState, type PointerEvent } from "react";
import {
  saveMask,
  selectMask,
  type MaskData,
  type SubjectPreview,
} from "@/lib/graph";
import { decodeMask, encodeMask } from "@/lib/mask-rle";

type Tool = "brush" | "lasso" | "rectangle" | "select";
type Point = { x: number; y: number };

export function MaskEditor({
  projectId,
  nodeId,
  subject,
  hasReferences = false,
  initialMask,
  onClose,
  onSave,
}: {
  projectId: string;
  nodeId: string;
  subject: SubjectPreview;
  initialMask: MaskData | null;
  hasReferences?: boolean;
  onClose: () => void;
  onSave: (mask: MaskData | null) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const gesture = useRef<{ points: Point[]; before: ImageData } | null>(null);
  const history = useRef<string[]>([]);
  const [tool, setTool] = useState<Tool>("brush");
  const [size, setSize] = useState(30);
  const [erase, setErase] = useState(false);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });
  const [count, setCount] = useState(() =>
    initialMask?.subject_version_id === subject.versionId
      ? initialMask.rle
          .trim()
          .split(/\s+/)
          .reduce(
            (sum, token, index) => sum + (index % 2 ? Number(token) : 0),
            0,
          )
      : 0,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");

  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  useEffect(() => {
    if (!dimensions.width) return;
    const context = canvas.current?.getContext("2d");
    if (
      !context ||
      !initialMask ||
      initialMask.subject_version_id !== subject.versionId
    )
      return;
    if (
      initialMask.width !== dimensions.width ||
      initialMask.height !== dimensions.height
    )
      return;
    context.putImageData(
      new ImageData(
        decodeMask(initialMask.rle, dimensions.width, dimensions.height),
        dimensions.width,
        dimensions.height,
      ),
      0,
      0,
    );
  }, [dimensions, initialMask, subject.versionId]);

  function currentMask() {
    const context = canvas.current!.getContext("2d")!;
    return encodeMask(
      context.getImageData(0, 0, dimensions.width, dimensions.height).data,
    );
  }
  function remember() {
    history.current.push(currentMask().rle);
    if (history.current.length > 12) history.current.shift();
  }
  function point(event: PointerEvent<HTMLCanvasElement>): Point {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(
        0,
        Math.min(
          dimensions.width - 1,
          ((event.clientX - rect.left) / rect.width) * dimensions.width,
        ),
      ),
      y: Math.max(
        0,
        Math.min(
          dimensions.height - 1,
          ((event.clientY - rect.top) / rect.height) * dimensions.height,
        ),
      ),
    };
  }
  async function select(points: { x: number; y: number; label: 0 | 1 }[]) {
    if (busy || text.length > 240) return;
    setBusy(true);
    setError(null);
    try {
      const mask = await selectMask(projectId, subject.versionId, text, points);
      if (!mask) {
        setError(
          "Nothing matched. Try another description or select the area by hand.",
        );
        return;
      }
      if (mask.width !== dimensions.width || mask.height !== dimensions.height)
        throw new Error("Selection dimensions do not match this input image");
      remember();
      canvas
        .current!.getContext("2d")!
        .putImageData(
          new ImageData(
            decodeMask(mask.rle, mask.width, mask.height),
            mask.width,
            mask.height,
          ),
          0,
          0,
        );
      setCount(currentMask().count);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Selection failed");
    } finally {
      setBusy(false);
    }
  }
  function draw(event: PointerEvent<HTMLCanvasElement>, finish = false) {
    const active = gesture.current;
    if (!active) return;
    const context = event.currentTarget.getContext("2d")!;
    const next = point(event),
      previous = active.points.at(-1)!;
    active.points.push(next);
    if (tool !== "brush") context.putImageData(active.before, 0, 0);
    context.globalCompositeOperation = erase
      ? "destination-out"
      : "source-over";
    context.strokeStyle = context.fillStyle = "#f97316";
    context.lineWidth = tool === "brush" ? size : 2;
    context.lineCap = context.lineJoin = "round";
    context.beginPath();
    if (tool === "rectangle") {
      const origin = active.points[0];
      context.rect(origin.x, origin.y, next.x - origin.x, next.y - origin.y);
      context.fill();
    } else if (tool === "lasso") {
      context.moveTo(active.points[0].x, active.points[0].y);
      for (const p of active.points.slice(1)) context.lineTo(p.x, p.y);
      if (finish) {
        context.closePath();
        context.fill();
      } else context.stroke();
    } else {
      context.moveTo(previous.x, previous.y);
      context.lineTo(next.x, next.y);
      context.stroke();
    }
    context.globalCompositeOperation = "source-over";
    setCount(currentMask().count);
  }
  async function save(clear = false) {
    setBusy(true);
    setError(null);
    try {
      if (!clear && hasReferences)
        throw new Error(
          "This node has references. Remove them to save an area selection.",
        );
      const encoded = currentMask();
      if (!clear && !encoded.count)
        throw new Error("Select an area first, or choose Remove selection.");
      const mask = clear
        ? null
        : {
            ...dimensions,
            rle: encoded.rle,
            subject_version_id: subject.versionId,
          };
      await saveMask(projectId, nodeId, mask);
      onSave(mask);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save area selection",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialog}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
      className="m-auto max-h-[94vh] w-[min(1100px,94vw)] overflow-auto rounded-2xl bg-white p-5 shadow-2xl backdrop:bg-black/60"
    >
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-semibold">
            Select an area of {subject.nodeTitle}
          </h2>
          <p className="text-xs text-neutral-500">
            Orange areas change.
          </p>
        </div>
        <button
          disabled={busy}
          onClick={onClose}
          aria-label="Close area selection editor"
        >
          ✕
        </button>
      </div>
      <div className="my-4 flex flex-wrap items-center gap-3">
        {(["brush", "lasso", "rectangle", "select"] as const).map((value) => (
          <button
            key={value}
            disabled={busy}
            aria-pressed={tool === value}
            className={`rounded-lg border px-3 py-1.5 text-sm capitalize ${tool === value ? "border-orange-500 bg-orange-50" : "border-neutral-200"}`}
            onClick={() => setTool(value)}
          >
            {value === "select" ? "SAM click" : value}
          </button>
        ))}
        <label className="text-sm">
          <input
            type="checkbox"
            checked={erase}
            onChange={(e) => setErase(e.target.checked)}
          />{" "}
          Erase
        </label>
        <label className="flex items-center gap-2 text-sm">
          Brush{" "}
          <input
            aria-label="Brush diameter"
            type="range"
            min="3"
            max="160"
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
          />
        </label>
        <button
          disabled={busy}
          onClick={() => {
            const rle = history.current.pop();
            if (rle === undefined) return;
            canvas
              .current!.getContext("2d")!
              .putImageData(
                new ImageData(
                  decodeMask(rle, dimensions.width, dimensions.height),
                  dimensions.width,
                  dimensions.height,
                ),
                0,
                0,
              );
            setCount(currentMask().count);
          }}
        >
          Undo
        </button>
        <button
          disabled={busy || !dimensions.width}
          onClick={() => {
            remember();
            canvas
              .current!.getContext("2d")!
              .clearRect(0, 0, dimensions.width, dimensions.height);
            setCount(0);
          }}
        >
          Clear selection
        </button>
      </div>
      <div
        className="relative mx-auto w-fit max-w-full"
        style={{ maxHeight: "62vh" }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={subject.artifactUrl}
          alt="Input image to select"
          draggable={false}
          className="block max-h-[62vh] max-w-full object-contain"
          onLoad={(event) => {
            const image = event.currentTarget;
            setDimensions({
              width: image.naturalWidth,
              height: image.naturalHeight,
            });
          }}
          onError={() => setError("The input image could not be loaded.")}
        />
        <canvas
          ref={canvas}
          width={dimensions.width}
          height={dimensions.height}
          className="absolute inset-0 h-full w-full touch-none opacity-50"
          style={{ cursor: busy ? "wait" : "crosshair" }}
          onPointerDown={(event) => {
            if (busy || !dimensions.width) return;
            const p = point(event);
            if (tool === "select") {
              void select([
                {
                  x: Math.floor(p.x),
                  y: Math.floor(p.y),
                  label: erase ? 0 : 1,
                },
              ]);
              return;
            }
            remember();
            event.currentTarget.setPointerCapture(event.pointerId);
            const context = event.currentTarget.getContext("2d")!;
            gesture.current = {
              points: [p],
              before: context.getImageData(
                0,
                0,
                dimensions.width,
                dimensions.height,
              ),
            };
            if (tool === "brush") {
              context.globalCompositeOperation = erase
                ? "destination-out"
                : "source-over";
              context.fillStyle = "#f97316";
              context.beginPath();
              context.arc(p.x, p.y, size / 2, 0, Math.PI * 2);
              context.fill();
              context.globalCompositeOperation = "source-over";
            }
          }}
          onPointerMove={(event) => draw(event)}
          onPointerUp={(event) => {
            draw(event, true);
            gesture.current = null;
            if (dimensions.width) setCount(currentMask().count);
          }}
          onPointerCancel={() => {
            if (gesture.current)
              canvas
                .current!.getContext("2d")!
                .putImageData(gesture.current.before, 0, 0);
            gesture.current = null;
          }}
        />
      </div>
      <form
        className="my-4 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void select([]);
        }}
      >
        <input
          aria-label="Area to select"
          placeholder="Describe an area, e.g. logo"
          className="flex-1 rounded-lg border px-3 py-2 text-sm"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <button
          disabled={busy || !text.trim() || text.length > 240}
          className="rounded-lg border px-3 text-sm"
        >
          {busy ? "Working…" : "Select"}
        </button>
        {text.length >= 200 ? (
          <span className="text-xs">{text.length} / 240</span>
        ) : null}
      </form>
      {count === dimensions.width * dimensions.height && count > 0 ? (
        <p className="text-sm text-amber-700">
          Selecting everything is the same as no selection — the run will edit
          the whole image.
        </p>
      ) : null}
      {initialMask && initialMask.subject_version_id !== subject.versionId ? (
        <p className="text-sm text-amber-700">
          Area selection belongs to a different image. Select it again or remove
          it.
        </p>
      ) : null}
      {initialMask &&
      dimensions.width > 0 &&
      (initialMask.width !== dimensions.width ||
        initialMask.height !== dimensions.height) ? (
        <p className="text-sm text-amber-700">
          The area selection dimensions do not match this image. Draw a new
          selection.
        </p>
      ) : null}
      {hasReferences ? (
        <p role="alert" className="text-sm text-red-700">
          This node has references. Remove them to save an area selection.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="my-2 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-3">
        <button
          disabled={busy || !dimensions.width}
          onClick={() => (hasReferences ? onClose() : void save(true))}
          className="rounded-lg border px-3 py-2 text-sm"
        >
          {hasReferences ? "Cancel" : "Remove selection"}
        </button>
        <button
          disabled={busy || !dimensions.width || hasReferences}
          onClick={() => void save()}
          className="rounded-lg bg-neutral-900 px-4 py-2 text-sm text-white"
        >
          Save area selection
        </button>
      </div>
    </dialog>
  );
}
