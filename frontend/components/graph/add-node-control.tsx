import type { GraphNodeType } from "@/lib/graph";

type AddNodeControlProps = {
  onAdd: (type: GraphNodeType) => void;
};

const nodeOptions: { label: string; type: GraphNodeType }[] = [
  { label: "Prompt", type: "prompt" },
  { label: "Image", type: "image" },
  { label: "3D", type: "model3d" },
];

export function AddNodeControl({ onAdd }: AddNodeControlProps) {
  return (
    <div
      aria-label="Add node"
      className="flex overflow-hidden rounded-[var(--radius-control)] border border-neutral-300 bg-white"
      role="group"
    >
      {nodeOptions.map((option) => (
        <button
          className="border-r border-neutral-200 px-3 py-2 text-xs font-medium text-neutral-700 last:border-r-0 hover:bg-neutral-100 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-accent"
          key={option.type}
          onClick={() => onAdd(option.type)}
          type="button"
        >
          + {option.label}
        </button>
      ))}
    </div>
  );
}
