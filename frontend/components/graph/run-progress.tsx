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
      ? "Waiting for a worker"
      : stage === "dispatching"
        ? "Uploading inputs and starting generation"
        : stage === "provider_pending"
          ? "Generating your image"
          : stage === "ingesting"
            ? "Saving the original image"
            : "Saving your draft and queueing";
  return (
    <div
      role="status"
      className="mt-2 rounded bg-sky-50 p-2 text-xs text-sky-900"
    >
      <p>
        {label} · {seconds}s
      </p>
      <p className="mt-1 text-[11px] text-sky-700">
        {seconds > 60
          ? "Taking longer than usual. You can leave this canvas; the run is saved."
          : "Image runs often take around 24 seconds. Your draft stays editable."}
      </p>
    </div>
  );
}
