import { decodeMask } from "./mask-rle.ts";
import type { MaskData } from "./graph";

export type LogoCrop = { dataUrl: string; width: number; height: number };
export type DecalPlacement = {
  meshIndex: number;
  position: [number, number, number];
  orientation: [number, number, number, number];
};
export type MeshDecal = {
  crop: LogoCrop;
  placement: DecalPlacement | null;
  // Fraction of the normalized model's longest dimension; aspect ratio is locked.
  size: number;
  rotation: number;
};

/** Download first, as DownloadButton does. A CORS failure precedes any paid selection. */
export async function readLogoSource(url: string, signal: AbortSignal) {
  const response = await fetch(url, { mode: "cors", signal });
  if (!response.ok)
    throw new Error("The source image could not be downloaded.");
  const objectUrl = URL.createObjectURL(await response.blob());
  try {
    const image = new Image();
    image.src = objectUrl;
    await image.decode();
    signal.throwIfAborted();
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    // Verify readability now, before enabling selection (including SVG subresources).
    context.getImageData(0, 0, 1, 1);
    return canvas;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function decodeLogoMask(
  mask: Pick<MaskData, "rle" | "width" | "height">,
) {
  if (
    !Number.isInteger(mask.width) ||
    !Number.isInteger(mask.height) ||
    mask.width < 1 ||
    mask.height < 1 ||
    mask.width > 4096 ||
    mask.height > 4096
  )
    throw new Error("Invalid selection dimensions");
  const pixels = decodeMask(mask.rle, mask.width, mask.height);
  let left = mask.width,
    top = mask.height,
    right = -1,
    bottom = -1;
  for (let y = 0; y < mask.height; y++) {
    for (let x = 0; x < mask.width; x++) {
      if (!pixels[(y * mask.width + x) * 4 + 3]) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x);
      bottom = Math.max(bottom, y);
    }
  }
  if (right < left)
    throw new Error("Nothing matched. Click another part of the logo.");
  return {
    pixels,
    left,
    top,
    width: right - left + 1,
    height: bottom - top + 1,
  };
}

/** Apply the synchronous RLE at source resolution, including holes and separate letters. */
export function cropLogo(source: HTMLCanvasElement, mask: MaskData): LogoCrop {
  if (mask.width !== source.width || mask.height !== source.height)
    throw new Error("Selection dimensions do not match the source image.");
  const bounds = decodeLogoMask(mask);
  const canvas = document.createElement("canvas");
  canvas.width = bounds.width;
  canvas.height = bounds.height;
  const context = canvas.getContext("2d")!;
  context.drawImage(source, -bounds.left, -bounds.top);
  const crop = context.getImageData(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < canvas.height; y++) {
    for (let x = 0; x < canvas.width; x++) {
      if (
        !bounds.pixels[
          ((y + bounds.top) * source.width + x + bounds.left) * 4 + 3
        ]
      )
        crop.data.fill(
          0,
          (y * canvas.width + x) * 4,
          (y * canvas.width + x) * 4 + 4,
        );
    }
  }
  context.putImageData(crop, 0, 0);
  return {
    dataUrl: canvas.toDataURL("image/png"),
    width: canvas.width,
    height: canvas.height,
  };
}
