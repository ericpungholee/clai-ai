import type { Project } from "@/lib/projects";

import { ProjectTile } from "./project-tile";

type ProjectGridProps = {
  projects: Project[];
};

export function ProjectGrid({ projects }: ProjectGridProps) {
  if (projects.length === 0) {
    return (
      <div className="empty-projects">
        <h2 className="text-base font-medium text-foreground">
          No projects yet
        </h2>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-x-5 gap-y-8 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {projects.map((project) => (
        <ProjectTile key={project.id} project={project} />
      ))}
    </div>
  );
}
