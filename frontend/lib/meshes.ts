import { apiRequest, browserApiUrl } from "./api";

type MeshIdentity = {
  version_id: string;
  attempt_id: string;
  texture: "no" | "standard";
  preview_url: string | null;
  elapsed_seconds: number | null;
};

export type MeshData = MeshIdentity &
  (
    | {
        status: "queued" | "dispatching" | "provider_pending" | "ingesting";
        artifact_url: null;
        error: null;
      }
    | { status: "complete"; artifact_url: string; error: null }
    | { status: "failed"; artifact_url: null; error: string }
  );

export async function requestMesh(
  projectId: string,
  versionId: string,
  create?: { texture: "no" | "standard"; attempt_id: string },
): Promise<MeshData | null> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/mesh`,
    create
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(create),
        }
      : { cache: "no-store" },
    "The 3D view is unavailable. Your image is unchanged.",
  );
}
