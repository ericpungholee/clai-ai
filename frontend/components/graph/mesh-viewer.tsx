"use client";

import { useEffect, useRef, useState } from "react";
import type { MeshScene } from "@/lib/mesh-scene";
import { DownloadButton } from "./download-button";
import { Skeleton } from "./skeleton";
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
  const previewCallback = useRef(onPreview);
  useEffect(() => {
    previewCallback.current = onPreview;
  }, [onPreview]);
  useEffect(() => {
    dialog.current?.showModal();
    let alive = true;
    requestMesh(projectId, version.id)
      .then((mesh) => {
        if (alive) {
          setState({ status: "ready", mesh });
        }
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
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      let finished = false;
      try {
        const latest = await requestMesh(projectId, version.id);
        finished = latest?.status === "complete" || latest?.status === "failed";
        if (alive) setState({ status: "ready", mesh: latest });
      } catch {
        /* Retry the existing job after transient network failures. */
      } finally {
        if (alive && !finished) timer = setTimeout(poll, 2000);
      }
    };
    timer = setTimeout(poll, 2000);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [projectId, version.id, waiting]);
  useEffect(() => {
    if (mesh?.status === "complete" && mesh.preview_url)
      previewCallback.current(version.id, mesh.preview_url);
  }, [mesh, version.id]);
  const create = async (regenerate = false) => {
    if (state.status === "submitting") return;
    setState({ status: "submitting" });
    try {
      setState({
        status: "ready",
        mesh: await requestMesh(projectId, version.id, {
          texture: "standard",
          attempt_id: crypto.randomUUID(),
          regenerate,
          model: "trellis",
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
      className="m-auto flex h-[85vh] w-[85vw] max-w-6xl flex-col rounded-xl bg-white p-5 backdrop:bg-black/60"
    >
      <header className="flex justify-between">
        <h2 className="font-semibold">3D view</h2>
        <div className="flex items-center gap-2">
          {mesh?.status === "complete" ? (
            <button onClick={() => void create(true)}>Regenerate 3D</button>
          ) : null}
          {mesh?.status === "complete" ? (
            <DownloadButton
              url={mesh.artifact_url}
              name={`clai-${version.id}`}
              extension="glb"
              label="Export GLB"
            />
          ) : null}
          <button onClick={onClose}>Close</button>
        </div>
      </header>
      <main className="relative mt-4 flex min-h-0 flex-1 flex-col items-center justify-center overflow-hidden rounded-lg bg-white">
        {mesh?.status === "complete" ? (
          <ModelView key={mesh.attempt_id} mesh={mesh} />
        ) : waiting ||
          state.status === "loading" ||
          state.status === "submitting" ? (
          <div className="relative h-full w-full" aria-busy>
            <Skeleton className="h-full w-full rounded-lg" />
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-white/85 to-transparent px-4 pb-4 pt-8 text-center">
              {waiting ? (
                <div role="status">
                  <p className="text-sm text-neutral-600">
                    {mesh.status === "queued"
                      ? "Queued"
                      : mesh.status === "ingesting"
                        ? "Saving"
                        : "Generating"}
                  </p>
                  <p className="mt-1 text-sm text-neutral-600">
                    Safe to close — this keeps running.
                  </p>
                </div>
              ) : (
                <p role="status" className="text-sm text-neutral-600">
                  {state.status === "loading"
                    ? "Checking saved 3D image…"
                    : "Queueing one 3D generation…"}
                </p>
              )}
            </div>
          </div>
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={version.artifact_url}
              alt="Image used for this image’s 3D view"
              className="mb-5 max-h-[45%] max-w-[60%] rounded object-contain"
            />
            <div className="max-w-lg text-center">
              {state.status === "error" || mesh?.status === "failed" ? (
                <p role="alert" className="mb-3 text-sm text-red-700">
                  {state.status === "error" ? state.message : mesh?.error}
                </p>
              ) : null}
              <button
                onClick={() => void create()}
                className="mt-4 rounded bg-neutral-900 px-4 py-2 text-sm font-bold text-white"
              >
                {mesh?.status === "failed" ? "Retry" : "Generate"} 3D
              </button>
            </div>
          </>
        )}
      </main>
      {mesh?.status === "complete" && mesh.texture === "no" ? (
        <div className="mt-3 flex items-center justify-between gap-4 rounded bg-white p-3 text-sm">
          <p>
            This saved model contains only the shape. Generate colors and print
            to use image textures.
          </p>
          <button
            onClick={() => void create()}
            className="shrink-0 rounded bg-neutral-900 px-4 py-2 text-white"
          >
            Generate with colors & print
          </button>
        </div>
      ) : null}
    </dialog>
  );
}

function ModelView({ mesh }: { mesh: MeshData & { status: "complete" } }) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<MeshScene | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    import("@/lib/mesh-scene")
      .then(({ createMeshScene }) => {
        if (!alive || !host.current) return;
        scene.current = createMeshScene(host.current, mesh.artifact_url, {
          loaded: () => {
            if (alive) setLoaded(true);
          },
          error: (message) => {
            if (alive) setError(message);
          },
          placed: () => {},
          autoPlaced: () => {},
        });
      })
      .catch(() => {
        if (alive)
          setError("The 3D viewer could not load. Close and reopen to retry.");
      });
    return () => {
      alive = false;
      scene.current?.dispose();
      scene.current = null;
    };
  }, [mesh.artifact_url]);
  return (
    <div className="relative h-full w-full" aria-busy={!loaded}>
      {!loaded && mesh.preview_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mesh.preview_url}
          alt="Stored mesh preview while the viewer loads"
          className="pointer-events-none absolute h-full w-full object-contain"
        />
      ) : null}
      {!loaded && !error ? (
        <p
          role="status"
          className="absolute left-3 top-3 z-10 rounded bg-white p-2 text-xs"
        >
          Loading 3D viewer…
        </p>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="absolute bottom-3 left-3 right-3 z-10 rounded bg-white p-3 text-sm text-red-700"
        >
          {error}
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => scene.current?.resetCamera()}
        disabled={!loaded}
        className="absolute right-3 top-3 z-10 rounded border bg-white px-3 py-1 text-xs disabled:opacity-50"
      >
        Reset view
      </button>
      <div ref={host} className="h-full w-full" />
    </div>
  );
}
