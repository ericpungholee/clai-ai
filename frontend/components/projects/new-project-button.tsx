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
        className="new-project-button text-white"
        aria-label={isCreating ? "Creating project" : "New Project"}
        title="New Project"
        aria-busy={isCreating}
        type="button"
        onClick={createProject}
        disabled={isCreating}
      >
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          {isCreating ? <path d="M5 12h.01M12 12h.01M19 12h.01" /> : <path d="M12 5v14M5 12h14" />}
        </svg>
      </button>
    </div>
  );
}
