import Link from "next/link";
import { notFound } from "next/navigation";

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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 shrink-0 items-center border-b border-border px-5 sm:px-7">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Link
            className="font-semibold text-foreground hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            href="/"
          >
            Clai
          </Link>
          <span className="text-neutral-300" aria-hidden="true">
            /
          </span>
          <h1 className="truncate font-medium text-foreground">{project.name}</h1>
        </div>
      </header>
      <main className="min-h-0 flex-1 bg-background" aria-label="Project canvas" />
    </div>
  );
}
