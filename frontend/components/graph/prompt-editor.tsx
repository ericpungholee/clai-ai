"use client";

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  referenceNumber,
  type ConnectPreview,
  type PromptPart,
} from "@/lib/graph";

type Candidate = { id: string; title: string };

function readDocument(root: HTMLElement): PromptPart[] {
  const parts: PromptPart[] = [];
  function addText(text: string) {
    const last = parts.at(-1);
    if (last?.type === "text") last.text += text;
    else if (text) parts.push({ type: "text", text });
  }
  function visit(node: ChildNode) {
    if (node.nodeType === Node.TEXT_NODE) {
      addText(node.textContent ?? "");
      return;
    }
    if (!(node instanceof HTMLElement)) return;
    if (node.dataset.edgeId && node.dataset.sourceId) {
      parts.push({
        type: "connect",
        edge_id: node.dataset.edgeId,
        source_node_id: node.dataset.sourceId,
      });
      return;
    }
    if (node.tagName === "BR") {
      addText("\n");
      return;
    }
    if (node.tagName === "DIV" && parts.length) addText("\n");
    node.childNodes.forEach(visit);
  }
  root.childNodes.forEach(visit);
  return parts;
}

function animateDeparture(chip: HTMLElement) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const box = chip.getBoundingClientRect();
  const copy = chip.cloneNode(true) as HTMLElement;
  copy.removeAttribute("data-edge-id");
  copy.removeAttribute("tabindex");
  copy.setAttribute("aria-hidden", "true");
  Object.assign(copy.style, {
    position: "fixed",
    left: `${box.left}px`,
    top: `${box.top}px`,
    width: `${box.width}px`,
    height: `${box.height}px`,
    pointerEvents: "none",
    zIndex: "100",
  });
  window.document.body.append(copy);
  const animation = copy.animate(
    [
      { opacity: 0.7, transform: "scale(1)" },
      { opacity: 0, transform: "scale(0.85)" },
    ],
    { duration: 150 },
  );
  void animation.finished.then(
    () => copy.remove(),
    () => copy.remove(),
  );
}

export function PromptEditor({
  document,
  connects,
  candidates,
  placeholder,
  hasSubject,
  highlightedWireId,
  footer,
  referenceHandle,
  onChange,
  onHover,
  onJump,
  onRun,
}: {
  document: PromptPart[];
  connects: ConnectPreview[];
  candidates: Candidate[];
  placeholder: string;
  hasSubject: boolean;
  highlightedWireId: string | null;
  footer: ReactNode;
  referenceHandle: ReactNode;
  onChange: (document: PromptPart[]) => void;
  onHover: (id: string | null) => void;
  onJump: (id: string) => void;
  onRun: () => void;
}) {
  const editor = useRef<HTMLDivElement>(null);
  const lastDocument = useRef("");
  const insertion = useRef<Range | null>(null);
  const [menu, setMenu] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const root = editor.current!;
    const serialized = JSON.stringify(document);
    if (serialized !== lastDocument.current) {
      root.querySelectorAll<HTMLElement>("[data-edge-id]").forEach((chip) => {
        if (
          !document.some(
            (part) =>
              part.type === "connect" && part.edge_id === chip.dataset.edgeId,
          )
        )
          animateDeparture(chip);
      });
      root.replaceChildren(
        ...document.map((part) => {
          if (part.type === "text")
            return window.document.createTextNode(part.text);
          const chip = window.document.createElement("span");
          chip.contentEditable = "false";
          chip.dataset.edgeId = part.edge_id;
          chip.dataset.sourceId = part.source_node_id;
          return chip;
        }),
      );
      lastDocument.current = serialized;
    }
    root.querySelectorAll<HTMLElement>("[data-edge-id]").forEach((chip) => {
      const ref = connects.find(
        (value) => value.edgeId === chip.dataset.edgeId,
      );
      const number = referenceNumber(
        connects.findIndex((value) => value.edgeId === chip.dataset.edgeId),
        hasSubject,
      );
      const label = ref?.title ?? "Deleted concept";
      const badge = window.document.createElement("span");
      badge.className = "wire-number";
      badge.textContent = String(number);
      const name = window.document.createElement("span");
      name.textContent = `@${label.length > 18 ? `${label.slice(0, 18)}…` : label}`;
      chip.replaceChildren(badge, name);
      chip.className = `prompt-chip ${ref?.state === "deleted" ? "broken" : ""}`;
      chip.dataset.highlighted = String(
        highlightedWireId === chip.dataset.edgeId,
      );
      chip.tabIndex = 0;
      chip.setAttribute("role", "button");
      chip.setAttribute("aria-label", `Image ${number}: ${label}`);
      chip.title =
        ref?.state === "deleted"
          ? "Source deleted — remove or replace this chip"
          : ref?.state === "empty"
            ? "Run the source node first"
            : "Click to find on canvas";
      chip.onmouseenter = () => onHover(chip.dataset.edgeId!);
      chip.onfocus = () => onHover(chip.dataset.edgeId!);
      chip.onblur = () => onHover(null);
      chip.onmouseleave = () => onHover(null);
      chip.onclick = () => onJump(chip.dataset.sourceId!);
      chip.onkeydown = (event) => {
        if (event.key === "Enter" && !event.metaKey && !event.ctrlKey) {
          event.preventDefault();
          event.stopPropagation();
          onJump(chip.dataset.sourceId!);
        }
        if (event.key === "Backspace" || event.key === "Delete") {
          event.preventDefault();
          event.stopPropagation();
          animateDeparture(chip);
          chip.remove();
          editor.current?.focus();
          const value = readDocument(root);
          lastDocument.current = JSON.stringify(value);
          onChange(value);
        }
      };
    });
  }, [
    document,
    connects,
    hasSubject,
    highlightedWireId,
    onHover,
    onJump,
    onChange,
  ]);

  function emit() {
    const value = readDocument(editor.current!);
    lastDocument.current = JSON.stringify(value);
    onChange(value);
  }
  function openMenu() {
    const selection = window.getSelection();
    if (!selection?.rangeCount) return;
    insertion.current = selection.getRangeAt(0).cloneRange();
    setQuery("");
    setMenu(true);
  }
  function insert(candidate: Candidate) {
    const range = insertion.current;
    if (!range) return;
    const chip = window.document.createElement("span");
    chip.contentEditable = "false";
    chip.dataset.edgeId = crypto.randomUUID();
    chip.dataset.sourceId = candidate.id;
    chip.textContent = `@${candidate.title}`;
    range.deleteContents();
    range.insertNode(chip);
    const space = window.document.createTextNode(" ");
    chip.after(space);
    range.setStartAfter(space);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    setMenu(false);
    editor.current!.focus();
    emit();
  }
  function key(event: KeyboardEvent<HTMLDivElement>) {
    event.stopPropagation();
    if (event.key === "@") {
      event.preventDefault();
      openMenu();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      onRun();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      window.document.execCommand("insertText", false, "\n");
      emit();
      return;
    }
    if (event.key !== "Backspace" && event.key !== "Delete") return;
    const selection = window.getSelection();
    if (!selection?.isCollapsed || !selection.anchorNode) return;
    const anchor = selection.anchorNode;
    const backwards = event.key === "Backspace";
    const offset = selection.anchorOffset;
    const neighbor =
      anchor.nodeType === Node.TEXT_NODE
        ? backwards && offset === 0
          ? anchor.previousSibling
          : !backwards && offset === anchor.textContent?.length
            ? anchor.nextSibling
            : null
        : anchor.childNodes[backwards ? offset - 1 : offset];
    if (neighbor instanceof HTMLElement && neighbor.dataset.edgeId) {
      event.preventDefault();
      animateDeparture(neighbor);
      neighbor.remove();
      emit();
    }
  }
  const available = candidates.filter(
    (candidate) =>
      !connects.some((ref) => ref.nodeId === candidate.id) &&
      candidate.title.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <div className="prompt-anchor nodrag nowheel relative rounded-lg border border-neutral-200 bg-white focus-within:border-neutral-600">
      {referenceHandle}
      <div
        ref={editor}
        role="textbox"
        aria-label="Design prompt"
        aria-multiline
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        className="prompt-editor max-h-32 min-h-16 overflow-y-auto whitespace-pre-wrap break-words px-2.5 py-2 text-sm leading-6 outline-none"
        onInput={emit}
        onKeyDown={key}
        onPaste={(event) => {
          event.preventDefault();
          window.document.execCommand(
            "insertText",
            false,
            event.clipboardData.getData("text/plain"),
          );
          emit();
        }}
      />
      <div className="flex h-9 items-center justify-end gap-2 px-2 pb-1">
        {footer}
      </div>
      {menu ? (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-1 rounded-lg border bg-white p-2 shadow-xl"
          role="dialog"
          aria-label="Connect a concept"
        >
          <input
            autoFocus
            aria-label="Find a concept"
            placeholder="Find a concept"
            className="w-full border-b p-1 text-xs outline-none"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              event.stopPropagation();
              if (event.key === "Escape") {
                setMenu(false);
                editor.current?.focus();
              }
              if (event.key === "Enter" && available[0] && connects.length < 2)
                insert(available[0]);
            }}
          />
          {connects.length >= 2 ? (
            <p className="p-2 text-xs">
              Two connect chips maximum. Remove one first.
            </p>
          ) : (
            available.map((candidate) => (
              <button
                key={candidate.id}
                type="button"
                className="block w-full truncate rounded px-2 py-1 text-left text-xs hover:bg-purple-50"
                onClick={() => insert(candidate)}
              >
                {candidate.title}
              </button>
            ))
          )}
          <button
            className="mt-1 text-xs text-neutral-500"
            onClick={() => {
              setMenu(false);
              editor.current?.focus();
            }}
          >
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}
