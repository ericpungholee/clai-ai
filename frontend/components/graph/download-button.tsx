"use client";

import { useState } from "react";

/** Download the stored artifact, preserving its bytes and actual file type. */
export function DownloadButton({ url, name, label = "Export image", extension }: {
  url: string;
  name: string;
  label?: string;
  extension?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function download() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error("Could not download the file. Please try again.");
      const blob = await response.blob();
      const types: Record<string, string> = {
        "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
        "image/svg+xml": "svg", "image/avif": "avif", "image/gif": "gif",
        "model/gltf-binary": "glb",
      };
      const suffix = extension ?? types[blob.type.split(";")[0]] ?? new URL(url, window.location.href).pathname.match(/\.([a-z0-9]+)$/i)?.[1] ?? "bin";
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `${name.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "").slice(0, 100) || "clai-export"}.${suffix}`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
    } catch (error) {
      setError(error instanceof Error ? error.message : "Download failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <span className="download-control nodrag nowheel">
      <button type="button" className="export-button" disabled={busy} onClick={() => void download()}>
        {busy ? "Exporting…" : label}
      </button>
      {error ? <span role="alert" className="download-error">{error}</span> : null}
    </span>
  );
}
