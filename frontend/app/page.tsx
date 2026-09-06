import { NewProjectButton } from "@/components/projects/new-project-button";
import { ProjectGrid } from "@/components/projects/project-grid";
import { getProjects } from "@/lib/projects";

export default async function Home() {
  const projects = await getProjects();

  return (
    <>
      <header className="app-header">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center justify-between px-5 sm:px-7">
          <span className="brand">Clai</span>
          <NewProjectButton />
        </div>
      </header>
      <main className="home-main mx-auto w-full max-w-[1440px] flex-1 px-5 sm:px-7">
        <div className="projects-heading"><h1>Projects <span>{projects.length}</span></h1></div>
        <ProjectGrid projects={projects} />
      </main>
    </>
  );
}
