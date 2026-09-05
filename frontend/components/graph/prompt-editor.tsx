"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { ConnectPreview, PromptPart } from "@/lib/graph";

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

export function PromptEditor({
  document,
  connects,
  candidates,
  placeholder,
  onChange,
  onHover,
  onJump,
  onRun,
}: {
  document: PromptPart[];
  connects: ConnectPreview[];
  candidates: Candidate[];
  placeholder: string;
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
      chip.textContent = `@${ref?.title ?? "Deleted concept"}`;
      chip.className = `mx-0.5 inline rounded px-1 py-0.5 text-xs ${ref?.state === "ready" ? "bg-purple-100 text-purple-900" : "bg-red-100 text-red-800"}`;
      chip.title =
        ref?.state === "deleted"
          ? "Source deleted — remove or replace this chip"
          : ref?.state === "empty"
            ? "Run the source node first"
            : "Click to find on canvas";
      chip.onmouseenter = () => onHover(chip.dataset.sourceId!);
      chip.onmouseleave = () => onHover(null);
      chip.onclick = () => onJump(chip.dataset.sourceId!);
    });
  }, [document, connects, onHover, onJump]);

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
    <div className="nodrag nowheel relative mt-3">
      <div
        ref={editor}
        role="textbox"
        aria-label="Design prompt"
        aria-multiline
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        className="prompt-editor max-h-52 min-h-20 overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-neutral-200 bg-white px-2.5 py-2 text-sm leading-6 outline-none focus:border-sky-400"
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
