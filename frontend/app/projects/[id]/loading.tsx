import Link from "next/link";

export default function ProjectLoading() {
  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-white">
      <header className="grid h-14 shrink-0 grid-cols-[1fr_minmax(0,auto)_1fr] items-center border-b border-border px-4 sm:px-6">
        <Link
          className="w-fit text-sm font-medium text-neutral-600 hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          href="/"
        >
          ← Projects
        </Link>
        <span className="text-sm font-semibold text-neutral-400">
          Loading project…
        </span>
      </header>
      <main className="min-h-0 flex-1 bg-neutral-50" />
    </div>
  );
}
