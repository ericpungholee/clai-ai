"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { OverflowMenu } from "@/components/graph/overflow-menu";
import { ConfirmDialog, type Confirmation } from "@/components/graph/confirm-dialog";
import { changeProject, type Project } from "@/lib/projects";

type ProjectTileProps = {
  project: Project;
};

function formatUpdatedAt(value: string): string {
  const updatedAt = new Date(value);
  const elapsedSeconds = Math.max(
    0,
    Math.floor((Date.now() - updatedAt.getTime()) / 1000),
  );

  if (elapsedSeconds < 60) {
    return "Updated just now";
  }

  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `Updated ${elapsedMinutes} minute${elapsedMinutes === 1 ? "" : "s"} ago`;
  }

  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) {
    return `Updated ${elapsedHours} hour${elapsedHours === 1 ? "" : "s"} ago`;
  }

  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 7) {
    return `Updated ${elapsedDays} day${elapsedDays === 1 ? "" : "s"} ago`;
  }

  return `Updated ${updatedAt.toLocaleDateString("en", {
    month: "short",
    day: "numeric",
    year:
      updatedAt.getFullYear() === new Date().getFullYear()
        ? undefined
        : "numeric",
  })}`;
}

export function ProjectTile({ project }: ProjectTileProps) {
  const router = useRouter();
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(project.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mutate = async (newName?: string) => {
    setBusy(true);
    setError(null);
    try {
      await changeProject(project.id, newName);
      setRenaming(false);
      router.refresh();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Project change failed",
      );
    } finally {
      setBusy(false);
    }
  };
  const thumbnailStyle = project.thumbnail_url
    ? { backgroundImage: `url("${project.thumbnail_url}")` }
    : undefined;

  return (
    <article className="project-tile" aria-label={project.name}>
      <Link
        className="group block rounded-[var(--radius-control)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
        href={`/projects/${project.id}`}
      >
        <div
          className="project-thumb-wrap aspect-[4/3] bg-cover bg-center"
          style={thumbnailStyle}
          role={project.thumbnail_url ? "img" : undefined}
          aria-label={
            project.thumbnail_url ? `${project.name} thumbnail` : undefined
          }
        >{!project.thumbnail_url ? <span className="project-placeholder" aria-hidden="true">✳</span> : null}</div>
        <div className="pt-2.5 pr-10">
          <h2 className="truncate text-[15px] font-medium text-foreground group-hover:text-accent">
            {project.name}
          </h2>
          <time
            className="mt-0.5 block text-sm text-muted"
            dateTime={project.updated_at}
          >
            {formatUpdatedAt(project.updated_at)}
          </time>
        </div>
      </Link>
      {renaming ? (
        <form
          className="project-rename mt-3 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) void mutate(name.trim());
          }}
        >
          <input
            aria-label="Project name"
            disabled={busy}
            autoFocus
            maxLength={120}
            value={name}
            className="min-w-0 flex-1 rounded border px-2 py-1 text-sm"
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape" && !busy) {
                setRenaming(false);
                setName(project.name);
              }
            }}
          />
          <button disabled={busy || !name.trim()} className="text-xs">
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => { setRenaming(false); setName(project.name); }}
            className="text-xs"
          >
            Cancel
          </button>
        </form>
      ) : (
        <OverflowMenu label={`Options for ${project.name}`} className="project-options">
          <button disabled={busy} onClick={() => { setName(project.name); setRenaming(true); }}>
            Rename
          </button>
          <button
            disabled={busy}
            onClick={() => {
              setConfirmation({
                message: `Delete “${project.name}” from your projects? Images and history will be retained.`,
                verb: "Delete project",
                resolve: (approved) => { if (approved) void mutate(); },
              });
            }}
          >
            Delete
          </button>
        </OverflowMenu>
      )}
      {confirmation ? <ConfirmDialog confirmation={confirmation} onClose={() => setConfirmation(null)} /> : null}
      {error ? (
        <p role="alert" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      ) : null}
    </article>
  );
}
