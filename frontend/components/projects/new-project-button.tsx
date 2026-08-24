"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function NewProjectButton() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createProject() {
    setIsCreating(true);
    setError(null);

    try {
      const response = await fetch(`${apiUrl}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Untitled Project" }),
      });

      if (!response.ok) {
        throw new Error();
      }

      const project: { id: string } = await response.json();
      router.push(`/projects/${project.id}`);
    } catch {
      setError("Could not create project");
      setIsCreating(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      {error && (
        <span className="text-sm text-red-700" role="alert">
          {error}
        </span>
      )}
      <button
        className="rounded-[var(--radius-control)] bg-accent px-3.5 py-2 text-sm font-medium text-white hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60"
        type="button"
        onClick={createProject}
        disabled={isCreating}
      >
        {isCreating ? "Creating…" : "New Project"}
      </button>
    </div>
  );
}
