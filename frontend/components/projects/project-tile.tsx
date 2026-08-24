import Link from "next/link";

import type { Project } from "@/lib/projects";

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
    year: updatedAt.getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  })}`;
}

export function ProjectTile({ project }: ProjectTileProps) {
  const thumbnailStyle = project.thumbnail_url
    ? { backgroundImage: `url("${project.thumbnail_url}")` }
    : undefined;

  return (
    <Link
      className="group block rounded-[var(--radius-control)] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-accent"
      href={`/projects/${project.id}`}
    >
      <div
        className="aspect-[4/3] rounded-[var(--radius-surface)] border border-border bg-surface-muted bg-cover bg-center group-hover:border-neutral-400 group-hover:bg-neutral-100"
        style={thumbnailStyle}
        role={project.thumbnail_url ? "img" : undefined}
        aria-label={project.thumbnail_url ? `${project.name} thumbnail` : undefined}
      />
      <div className="pt-2.5">
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
  );
}
