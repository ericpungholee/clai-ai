"use client";
import { useEffect, useRef } from "react";
const invariants = [
  "A node is a draft until a run succeeds. Then it is a result, and its prompt, inputs, settings, and area selection are frozen forever.",
  "One node, one image.",
  "Every change makes a new node.",
  "The canvas is the history. No per-node version strip, no active-image pointer, no hidden images.",
  "No image ever changes after it is made, so nothing downstream can go stale.",
  "Saving an area selection arms the node. Only Run generates.",
];
const shortcuts = [
  ["N", "New node"],
  ["B", "New connected node"],
  ["Cmd/Ctrl+D", "Duplicate draft"],
  ["Cmd/Ctrl+Enter", "Run"],
  ["@", "Add a reference"],
  ["F", "Frame whole graph"],
  ["Shift", "Select nodes"],
  ["Space", "Pan"],
  ["Delete", "Delete selection"],
  ["Escape", "Close"],
];
export function HelpPanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      onCancel={onClose}
      className="m-auto max-h-[90vh] max-w-xl overflow-auto rounded-xl bg-white p-6 backdrop:bg-black/50"
    >
      <h2 className="font-semibold">How Clai works</h2>
      <ol className="my-4 list-decimal space-y-2 pl-5 text-sm">
        {invariants.map((rule) => (
          <li key={rule}>{rule}</li>
        ))}
      </ol>
      <table className="w-full text-left text-sm">
        <caption className="mb-2 text-left font-semibold">
          Keyboard shortcuts
        </caption>
        <tbody>
          {shortcuts.map(([key, action]) => (
            <tr key={key}>
              <th className="py-1 pr-4">{key}</th>
              <td>{action}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="mt-4 rounded border px-3 py-1" onClick={onClose}>
        Close
      </button>
    </dialog>
  );
}
