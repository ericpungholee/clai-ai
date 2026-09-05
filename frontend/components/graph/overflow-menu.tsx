"use client";
import { useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./icon";

const subscribe = () => () => {};
export function OverflowMenu({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const trigger = useRef<HTMLButtonElement>(null);
  const popover = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  return (
    <span className={`nodrag overflow-menu ${className}`}>
      <button
        ref={trigger}
        type="button"
        aria-label={label}
        title={label}
        className="icon-button"
        onClick={() => {
          const bounds = trigger.current!.getBoundingClientRect();
          setPosition({
            left: Math.min(
              window.innerWidth - 232,
              Math.max(8, bounds.right - 220),
            ),
            top: Math.min(window.innerHeight - 280, bounds.bottom + 4),
          });
          popover.current?.togglePopover();
          popover.current?.querySelector("button")?.focus();
        }}
      >
        <Icon name="more" />
      </button>
      {mounted
        ? createPortal(
            <div
              ref={popover}
              popover="auto"
              aria-label={label}
              className="overflow-menu-content nodrag nowheel"
              style={{ position: "fixed", margin: 0, ...position }}
              onKeyDown={(event) => {
                event.stopPropagation();
                if (event.key === "Escape") {
                  event.preventDefault();
                  popover.current?.hidePopover();
                  trigger.current?.focus();
                }
              }}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("button")) {
                  popover.current?.hidePopover();
                  trigger.current?.focus();
                }
              }}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}
