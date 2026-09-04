import Link from "next/link";
import { notFound } from "next/navigation";

import { GraphWorkspace } from "@/components/graph/graph-workspace";
import { getGraph } from "@/lib/graph";
import { getProject } from "@/lib/projects";

type ProjectPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { id } = await params;
  const project = await getProject(id);

  if (!project) {
    notFound();
  }

  let graph;

  try {
    graph = await getGraph(id);
  } catch (error) {
    console.error(`Failed to load graph for project ${id}`, error);
    return (
      <div className="flex h-dvh min-h-0 flex-col bg-white">
        <header className="grid h-14 shrink-0 grid-cols-[1fr_minmax(0,auto)_1fr] items-center border-b border-border px-4 sm:px-6">
          <Link
            className="w-fit text-sm font-medium text-neutral-600 hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            href="/"
          >
            ← Projects
          </Link>
          <h1 className="max-w-[45vw] truncate text-sm font-semibold text-foreground">
            {project.name}
          </h1>
        </header>
        <main className="flex min-h-0 flex-1 items-center justify-center px-5">
          <div>
            <h2 className="text-base font-semibold">Graph unavailable</h2>
            <p className="mt-1.5 text-sm text-muted">
              The project graph could not be loaded. Refresh to try again.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <GraphWorkspace
      initialGraph={graph}
      projectId={project.id}
      projectName={project.name}
    />
  );
}
