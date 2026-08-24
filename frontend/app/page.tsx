import { NewProjectButton } from "@/components/projects/new-project-button";
import { ProjectGrid } from "@/components/projects/project-grid";
import { getProjects } from "@/lib/projects";

export default async function Home() {
  const projects = await getProjects();

  return (
    <>
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-5 sm:px-7">
          <span className="text-base font-semibold tracking-[-0.01em]">Clai</span>
          <NewProjectButton />
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1440px] flex-1 px-5 py-7 sm:px-7">
        <h1 className="mb-6 text-xl font-semibold tracking-[-0.01em]">
          Projects
        </h1>
        <ProjectGrid projects={projects} />
      </main>
    </>
  );
}
