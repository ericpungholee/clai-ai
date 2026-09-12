import type { NodeRunState } from "@/lib/graph";

export function RunProgress({
  run,
}: {
  run: NodeRunState & { status: "running" };
}) {
  const stage = run.job?.status;
  const label =
    stage === "queued"
      ? "Queued"
      : stage === "dispatching"
        ? "Starting"
        : stage === "provider_pending"
          ? "Generating"
          : stage === "ingesting"
            ? "Saving image"
            : "Saving draft";
  return (
    <p role="status" className="text-xs text-neutral-500">
      {label}
    </p>
  );
}
