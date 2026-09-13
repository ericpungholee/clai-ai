import { apiRequest, browserApiUrl } from "./api";
import type { MeshDecal } from "./mesh-decals";

export type LogoPreservation = {
  status: "ready" | "not_found" | "failed" | "removed";
  decal: MeshDecal | null;
};

type MeshIdentity = {
  model?: string;
  version_id: string;
  attempt_id: string;
  texture: "no" | "standard";
  preview_url: string | null;
  elapsed_seconds: number | null;
  logo_preservation?: LogoPreservation | null;
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
  create?: { texture: "no" | "standard"; attempt_id: string; regenerate?: boolean; model?: "trellis" },
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

export async function saveMeshLogo(
  projectId: string,
  versionId: string,
  attemptId: string,
  decal: MeshDecal | null,
): Promise<LogoPreservation> {
  return apiRequest(
    `${browserApiUrl}/api/projects/${projectId}/versions/${versionId}/mesh/logo`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attempt_id: attemptId, decal }),
    },
    "The logo could not be saved. Adjust it again to retry before closing.",
  );
}
