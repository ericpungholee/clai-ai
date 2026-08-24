import Link from "next/link";

export default function ProjectNotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-14 items-center border-b border-border px-5 sm:px-7">
        <Link
          className="text-sm font-semibold hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          href="/"
        >
          Clai
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-5">
        <div>
          <h1 className="text-lg font-semibold">Project not found</h1>
          <p className="mt-1.5 text-sm text-muted">
            This project does not exist.
          </p>
          <Link
            className="mt-4 inline-block text-sm font-medium text-accent hover:text-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            href="/"
          >
            Return to projects
          </Link>
        </div>
      </main>
    </div>
  );
}
