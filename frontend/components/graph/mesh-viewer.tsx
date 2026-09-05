"use client";

import { useEffect, useRef, useState } from "react";
import type { ModelViewerElement } from "@google/model-viewer";
import type { Version } from "@/lib/graph";
import { requestMesh, type MeshData } from "@/lib/meshes";

type LoadState =
  | { status: "loading" | "submitting" }
  | { status: "ready"; mesh: MeshData | null }
  | { status: "error"; message: string };

export function MeshViewer({
  projectId,
  version,
  onClose,
  onPreview,
}: {
  projectId: string;
  version: Version;
  onClose: () => void;
  onPreview: (versionId: string, url: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [textured, setTextured] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const previewCallback = useRef(onPreview);
  useEffect(() => {
    previewCallback.current = onPreview;
  }, [onPreview]);
  useEffect(() => {
    dialog.current?.showModal();
    let alive = true;
    requestMesh(projectId, version.id)
      .then((mesh) => {
        if (alive) setState({ status: "ready", mesh });
      })
      .catch((error) => {
        if (alive) setState({ status: "error", message: error.message });
      });
    return () => {
      alive = false;
    };
  }, [projectId, version.id]);
  const mesh = state.status === "ready" ? state.mesh : null;
  const waiting =
    mesh !== null && mesh.status !== "complete" && mesh.status !== "failed";
  useEffect(() => {
    if (!waiting) return;
    let alive = true;
    const timer = setInterval(() => {
      setSeconds((value) => value + 2);
      requestMesh(projectId, version.id)
        .then((mesh) => {
          if (alive) setState({ status: "ready", mesh });
        })
        .catch(() => {
          /* Keep polling the existing job, never submit another on a network error. */
        });
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [projectId, version.id, waiting]);
  useEffect(() => {
    if (mesh?.status === "complete" && mesh.preview_url)
      previewCallback.current(version.id, mesh.preview_url);
  }, [mesh, version.id]);
  const create = async () => {
    if (state.status === "submitting") return;
    setState({ status: "submitting" });
    setSeconds(0);
    try {
      setState({
        status: "ready",
        mesh: await requestMesh(projectId, version.id, {
          texture: textured ? "standard" : "no",
          attempt_id: crypto.randomUUID(),
        }),
      });
    } catch (error) {
      setState({
        status: "error",
        message:
          error instanceof Error
            ? error.message
            : "The 3D view could not be queued",
      });
    }
  };
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      className="m-auto flex h-[85vh] w-[85vw] max-w-6xl flex-col rounded-xl bg-neutral-50 p-5 backdrop:bg-black/60"
    >
      <header className="flex justify-between">
        <h2 className="font-semibold">
          3D form view ·{" "}
          {mesh?.texture === "standard" ? "textured" : "untextured"}
        </h2>
        <button onClick={onClose}>Back to canvas · Esc</button>
      </header>
      <p className="mt-2 rounded bg-amber-50 p-3 text-sm text-amber-900">
        The rear and hidden sides are inferred, not designed. This is a
        single-image form study, not CAD or a manufacturable mesh.
      </p>
      <main className="relative mt-4 flex min-h-0 flex-1 flex-col items-center justify-center overflow-hidden rounded-lg bg-neutral-200">
        {mesh?.status === "complete" ? (
          <GlbView key={version.id} mesh={mesh} />
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={version.artifact_url}
              alt="Image used for this version's 3D view"
              className="mb-5 max-h-[45%] max-w-[60%] rounded object-contain"
            />
            {waiting ? (
              <div role="status" className="text-center">
                <p>
                  {mesh.status === "queued"
                    ? "Queued"
                    : mesh.status === "ingesting"
                      ? "Saving the mesh and preview"
                      : "Generating the 3D form"}{" "}
                  · {seconds}s in this view
                </p>
                <p className="mt-2 text-sm text-neutral-600">
                  This is slower than an image edit. You can close this view;
                  the job keeps running.
                </p>
              </div>
            ) : state.status === "loading" || state.status === "submitting" ? (
              <p role="status">
                {state.status === "loading"
                  ? "Checking this version’s cache…"
                  : "Queueing one 3D generation…"}
              </p>
            ) : (
              <div className="max-w-lg text-center">
                {state.status === "error" || mesh?.status === "failed" ? (
                  <p role="alert" className="mb-3 text-sm text-red-700">
                    {state.status === "error" ? state.message : mesh?.error}
                  </p>
                ) : null}
                <p className="mb-3 text-sm">
                  Generate once, then reuse this version’s cached view.
                  Generation latency has not yet been verified.
                </p>
                <label className="flex items-center justify-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={textured}
                    onChange={(event) => setTextured(event.target.checked)}
                  />
                  Standard textures · $0.30 instead of $0.20
                </label>
                <button
                  onClick={create}
                  className="mt-4 rounded bg-neutral-900 px-4 py-2 text-sm text-white"
                >
                  {mesh?.status === "failed" ? "Retry" : "Generate"} 3D · $
                  {textured ? "0.30" : "0.20"}
                </button>
                <p className="mt-2 text-xs text-neutral-500">
                  Grey geometry is the default. No HD, style or quad-mesh
                  surcharges.
                </p>
              </div>
            )}
          </>
        )}
      </main>
      {mesh?.status === "complete" ? (
        <p className="mt-2 text-xs text-neutral-500">
          Cached for this exact image version.{" "}
          {mesh.elapsed_seconds !== null
            ? `Generated and saved in ${Math.round(mesh.elapsed_seconds)}s.`
            : ""}{" "}
          Drag to rotate; scroll to zoom.
        </p>
      ) : null}
    </dialog>
  );
}

function GlbView({ mesh }: { mesh: MeshData & { status: "complete" } }) {
  const host = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    let viewer: ModelViewerElement | null = null;
    import("@google/model-viewer")
      .then((module) => {
        if (!alive) return;
        // One active viewer and one retained model prevent a large canvas multiplying GPU use.
        module.ModelViewerElement.modelCacheSize = 1;
        viewer = document.createElement("model-viewer");
        viewer.src = mesh.artifact_url;
        viewer.alt = "Inferred 3D form; hidden surfaces were not specified";
        viewer.cameraControls = true;
        viewer.shadowIntensity = 0.4;
        viewer.style.width = "100%";
        viewer.style.height = "100%";
        if (mesh.preview_url) viewer.poster = mesh.preview_url;
        viewer.addEventListener("load", () => {
          if (alive) setLoaded(true);
        });
        viewer.addEventListener("error", () => {
          if (alive)
            setError(
              "This browser could not display the mesh. The cached file and original image are safe.",
            );
        });
        host.current?.replaceChildren(viewer);
      })
      .catch(() => {
        if (alive)
          setError("The 3D viewer could not load. Your image is unchanged.");
      });
    return () => {
      alive = false;
      viewer?.remove();
    };
  }, [mesh.artifact_url, mesh.preview_url]);
  return (
    <>
      {!loaded && mesh.preview_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mesh.preview_url}
          alt="Stored mesh preview while the viewer loads"
          className="pointer-events-none absolute h-full w-full object-contain"
        />
      ) : null}
      {error ? (
        <p
          role="alert"
          className="absolute z-10 rounded bg-white p-3 text-sm text-red-700"
        >
          {error}
        </p>
      ) : null}
      <div ref={host} className="h-full w-full" />
    </>
  );
}
