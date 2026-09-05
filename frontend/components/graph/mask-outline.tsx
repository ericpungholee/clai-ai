"use client";

import { useEffect, useRef } from "react";
import type { MaskData } from "@/lib/graph";
import { decodeMask } from "@/lib/mask-rle";

export function MaskOutline({ mask }: { mask: MaskData }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    const pixels = decodeMask(mask.rle, mask.width, mask.height);
    const outline = context.createImageData(mask.width, mask.height);
    const selected = (x: number, y: number) =>
      x >= 0 &&
      y >= 0 &&
      x < mask.width &&
      y < mask.height &&
      pixels[(y * mask.width + x) * 4 + 3] > 0;
    const thickness = Math.max(1, Math.round(mask.width / 140));
    for (let y = 0; y < mask.height; y++)
      for (let x = 0; x < mask.width; x++) {
        if (
          selected(x, y) &&
          (!selected(x - thickness, y) ||
            !selected(x + thickness, y) ||
            !selected(x, y - thickness) ||
            !selected(x, y + thickness))
        )
          outline.data.set([249, 115, 22, 255], (y * mask.width + x) * 4);
      }
    context.putImageData(outline, 0, 0);
  }, [mask]);
  return (
    <canvas
      ref={canvas}
      width={mask.width}
      height={mask.height}
      aria-label="Saved area selection"
      className="pointer-events-none absolute inset-0 h-full w-full object-contain"
    />
  );
}
