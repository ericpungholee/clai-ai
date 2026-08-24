"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type CheckState = "checking" | "ok" | "error";

export function BackendStatus() {
  const [state, setState] = useState<CheckState>("checking");
  const [detail, setDetail] = useState("Waiting for FastAPI /health");

  useEffect(() => {
    const controller = new AbortController();

    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const body = (await response.json()) as { status?: string };
        setState("ok");
        setDetail(`Reached ${API_URL}/health (${body.status ?? "ok"})`);
      })
      .catch((error: Error) => {
        if (error.name === "AbortError") {
          return;
        }
        setState("error");
        setDetail(`Could not reach ${API_URL}/health: ${error.message}`);
      });

    return () => controller.abort();
  }, []);

  return (
    <p>
      Backend: {state === "checking" && "checking…"}
      {state === "ok" && "reachable"}
      {state === "error" && "unreachable"}
      <span className="mt-2 block text-sm text-zinc-500">{detail}</span>
    </p>
  );
}
