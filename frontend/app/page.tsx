import { BackendStatus } from "./backend-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-xl flex-col justify-center gap-4 px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-tight">Clai</h1>
      <p>Frontend is running.</p>
      <BackendStatus />
    </main>
  );
}
