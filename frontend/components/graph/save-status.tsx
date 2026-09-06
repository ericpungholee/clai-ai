export type SaveState = "saved" | "saving" | "failed";
export const saveLabels: Record<SaveState, string> = {
  saved: "Saved",
  saving: "Saving…",
  failed: "Save failed",
};
export function SaveStatus({ state }: { state: SaveState }) {
  return (
    <span
      aria-label={saveLabels[state]}
      title={saveLabels[state]}
      aria-live="polite"
      role="status"
      className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full justify-self-end ${state === "failed" ? "bg-red-600" : state === "saving" ? "bg-amber-500" : "bg-neutral-400"}`}
    />
  );
}
