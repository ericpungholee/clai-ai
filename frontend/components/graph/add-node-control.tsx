type AddNodeControlProps = {
  onAdd: () => void;
};

export function AddNodeControl({ onAdd }: AddNodeControlProps) {
  return (
    <button
      className="rounded-[var(--radius-control)] border border-neutral-300 bg-white px-3 py-2 text-xs font-medium text-neutral-700 hover:bg-neutral-100 focus-visible:outline-2 focus-visible:outline-accent"
      onClick={onAdd}
      type="button"
    >
      Add node
    </button>
  );
}
