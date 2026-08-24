export type Project = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  thumbnail_url: string | null;
};

const apiUrl =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export async function getProjects(): Promise<Project[]> {
  const response = await fetch(`${apiUrl}/api/projects`, { cache: "no-store" });

  if (!response.ok) {
    throw new Error("Unable to load projects");
  }

  return response.json();
}

export async function getProject(id: string): Promise<Project | null> {
  const response = await fetch(`${apiUrl}/api/projects/${id}`, {
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
