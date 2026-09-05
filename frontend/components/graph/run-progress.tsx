"use client";
import { useEffect, useState } from "react";
import type { NodeRunState } from "@/lib/graph";
export function RunProgress({
  run,
}: {
  run: NodeRunState & { status: "running" };
}) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds =
    now === null
      ? 0
      : Math.max(0, Math.round((now - Date.parse(run.startedAt)) / 1000));
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
    <div
      role="status"
      className="flex w-full items-center justify-between text-xs text-neutral-500"
    >
      <span>{label}</span>
      <span className="tabular-nums">{seconds}s</span>
    </div>
  );
}
