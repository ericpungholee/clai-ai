"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { changeProject } from "@/lib/projects";

export function ProjectName({ id, name }: { id: string; name: string }) {
  const router = useRouter();
  const [savedName, setSavedName] = useState(name);
  const [draft, setDraft] = useState(name);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const skipBlur = useRef(false);

  function stopEditing(nextDraft = savedName) {
    skipBlur.current = true;
    setEditing(false);
    setError(null);
    setDraft(nextDraft);
  }

  async function save() {
    const nextName = draft.trim();
    if (busy) return;
    if (!nextName || nextName === savedName) {
      stopEditing(savedName);
      return;
    }
    skipBlur.current = true;
    setBusy(true);
    setError(null);
    try {
      await changeProject(id, nextName);
      setSavedName(nextName);
      stopEditing(nextName);
      router.refresh();
    } catch (error) {
      skipBlur.current = false;
      setError(error instanceof Error ? error.message : "Could not rename project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace-project-name">
      {editing ? (
        <input
          aria-label="Project name"
          autoFocus
          className="workspace-title min-w-0 w-full text-sm font-semibold"
          disabled={busy}
          maxLength={120}
          onBlur={() => {
            if (skipBlur.current) {
              skipBlur.current = false;
              return;
            }
            void save();
          }}
          onChange={(event) => setDraft(event.target.value)}
          onFocus={(event) => event.currentTarget.select()}
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === "Enter") {
              event.preventDefault();
              void save();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              stopEditing();
            }
          }}
          value={draft}
        />
      ) : (
        <h1 className="truncate text-sm font-semibold text-foreground">
          <button
            aria-label={`Rename project: ${savedName}`}
            className="workspace-title"
            onClick={() => {
              skipBlur.current = false;
              setDraft(savedName);
              setEditing(true);
            }}
            title="Rename project"
          >
            {savedName}
          </button>
        </h1>
      )}
      {error ? <p role="alert" className="project-name-error">{error}</p> : null}
    </div>
  );
}
