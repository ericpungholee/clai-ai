"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createProject } from "@/lib/projects";

export function NewProjectButton() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setIsCreating(true);
    setError(null);

    try {
      const project = await createProject();
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
        onClick={handleCreate}
        disabled={isCreating}
      >
        <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          {isCreating ? <path d="M5 12h.01M12 12h.01M19 12h.01" /> : <path d="M12 5v14M5 12h14" />}
        </svg>
      </button>
    </div>
  );
}
