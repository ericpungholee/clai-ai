export function decodeMask(
  rle: string,
  width: number,
  height: number,
): Uint8ClampedArray<ArrayBuffer> {
  const pixels = new Uint8ClampedArray(width * height * 4);
  const pairs = rle.trim() ? rle.trim().split(/\s+/).map(Number) : [];
  if (pairs.length % 2) throw new Error("Invalid mask encoding");
  let previousEnd = 0;
  for (let i = 0; i < pairs.length; i += 2) {
    const start = pairs[i] - 1,
      end = start + pairs[i + 1];
    if (
      !Number.isInteger(start) ||
      !Number.isInteger(end) ||
      start < previousEnd ||
      end <= start ||
      end > width * height
    ) {
      throw new Error("Mask extends beyond the subject image");
    }
    for (let pixel = start; pixel < end; pixel++) {
      pixels.set([249, 115, 22, 255], pixel * 4);
    }
    previousEnd = end;
  }
  return pixels;
}

export function encodeMask(pixels: Uint8ClampedArray): {
  rle: string;
  count: number;
} {
  const runs: number[] = [];
  let start = -1,
    count = 0;
  for (let i = 0; i <= pixels.length / 4; i++) {
    const selected = i < pixels.length / 4 && pixels[i * 4 + 3] >= 128;
    if (selected) count++;
    if (selected && start < 0) start = i;
    if (!selected && start >= 0) {
      runs.push(start + 1, i - start);
      start = -1;
    }
  }
  return { rle: runs.join(" "), count };
}
