import { apiRequest, browserApiUrl, serverApiUrl } from "./api";

export type Project = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  thumbnail_url: string | null;
};

export async function getProjects(): Promise<Project[]> {
  const response = await fetch(`${serverApiUrl}/api/projects`, { cache: "no-store" });

  if (!response.ok) {
    throw new Error("Unable to load projects");
  }

  return response.json();
}

export async function getProject(id: string): Promise<Project | null> {
  const response = await fetch(`${serverApiUrl}/api/projects/${id}`, {
    cache: "no-store",
  });

  if (response.status === 404 || response.status === 422) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Unable to load project");
  }

  return response.json();
}

export async function changeProject(id: string, name?: string): Promise<void> {
  const response = await fetch(
    `${browserApiUrl}/api/projects/${id}`,
    name === undefined
      ? { method: "DELETE" }
      : {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        },
  );
  if (!response.ok)
    throw new Error(
      name === undefined
        ? "Could not delete project"
        : "Could not rename project",
    );
}

export async function createProject(): Promise<Project> {
  return apiRequest(`${browserApiUrl}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "Untitled Project" }),
  });
}
