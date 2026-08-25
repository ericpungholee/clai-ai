export type SaveState = "saved" | "saving" | "failed";

type SaveStatusProps = {
  state: SaveState;
};

const labels: Record<SaveState, string> = {
  saved: "Saved",
  saving: "Saving…",
  failed: "Save failed",
};

export function SaveStatus({ state }: SaveStatusProps) {
  return (
    <span
      aria-live="polite"
      className={`justify-self-end text-xs ${
        state === "failed" ? "text-red-700" : "text-muted"
      }`}
      role="status"
    >
      {labels[state]}
    </span>
  );
}
