"use client";

import { useEffect, useRef } from "react";

export type Confirmation = {
  message: string;
  verb: string;
  resolve: (approved: boolean) => void;
};

export function ConfirmDialog({
  confirmation,
  onClose,
}: {
  confirmation: Confirmation;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    cancel.current?.focus();
  }, []);
  const finish = (approved: boolean) => {
    confirmation.resolve(approved);
    onClose();
  };
  return (
    <dialog
      ref={dialog}
      aria-label={confirmation.message}
      onCancel={(event) => {
        event.preventDefault();
        finish(false);
      }}
      className="m-auto max-w-md rounded-lg border border-neutral-200 bg-white p-5 shadow-xl backdrop:bg-black/30"
    >
      <p className="text-sm text-neutral-800">{confirmation.message}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button
          ref={cancel}
          className="rounded border px-3 py-1.5 text-sm"
          onClick={() => finish(false)}
        >
          Cancel
        </button>
        <button
          className="rounded bg-red-700 px-3 py-1.5 text-sm text-white"
          onClick={() => finish(true)}
        >
          {confirmation.verb}
        </button>
      </div>
    </dialog>
  );
}
