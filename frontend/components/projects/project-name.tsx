"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { changeProject } from "@/lib/projects";

export function ProjectName({ id, name }: { id: string; name: string }) {
  const router = useRouter();
  const [savedName, setSavedName] = useState(name);
  const [draft, setDraft] = useState(name);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function cancel() {
    if (busy) return;
    setEditing(false);
    setError(null);
    setDraft(savedName);
  }

  async function save() {
    const nextName = draft.trim();
    if (busy || !nextName) return;
    if (nextName === savedName) { cancel(); return; }
    setBusy(true);
    setError(null);
    try {
      await changeProject(id, nextName);
      setSavedName(nextName);
      setEditing(false);
      router.refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not rename project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace-project-name">
      {editing ? (
        <form
          className="project-rename flex items-center gap-2"
          onSubmit={(event) => { event.preventDefault(); void save(); }}
          onKeyDown={(event) => {
            event.stopPropagation();
            if (event.key === "Escape") { event.preventDefault(); cancel(); }
          }}
        >
          <input
            aria-label="Project name"
            autoFocus
            onFocus={(event) => event.currentTarget.select()}
            value={draft}
            maxLength={120}
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            className="min-w-0 w-full px-2 py-1 text-sm"
          />
          <button type="submit" aria-label="Save project name" title="Save" disabled={busy || !draft.trim()}>✓</button>
          <button type="button" aria-label="Cancel rename" title="Cancel" disabled={busy} onClick={cancel}>×</button>
        </form>
      ) : (
        <h1 className="truncate text-sm font-semibold text-foreground">
          <button className="workspace-title" title="Rename project" aria-label={`Rename project: ${savedName}`} onClick={() => { setDraft(savedName); setEditing(true); }}>
            {savedName}
          </button>
        </h1>
      )}
      {error ? <p role="alert" className="project-name-error">{error}</p> : null}
    </div>
  );
}
