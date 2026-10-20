"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * A modal confirmation. Pass `typeToConfirm` (e.g. "DELETE") to make the user type a word
 * before the button is enabled: used for destructive actions such as deleting a profile.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busy = false,
  typeToConfirm,
  danger = true,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  typeToConfirm?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [typed, setTyped] = useState("");
  const firstFocus = useRef<HTMLInputElement & HTMLButtonElement>(null);
  const ready = !typeToConfirm || typed.trim() === typeToConfirm;

  useEffect(() => {
    firstFocus.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <div className="modal-back" role="presentation" onClick={() => !busy && onCancel()}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-title">{title}</h2>
        <div className="muted">{children}</div>
        {typeToConfirm && (
          <div className="field" style={{ marginTop: 14, marginBottom: 0 }}>
            <label className="label" htmlFor="confirm-text">
              Type <strong>{typeToConfirm}</strong> to confirm
            </label>
            <input
              id="confirm-text"
              ref={firstFocus}
              className="input"
              autoComplete="off"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
          </div>
        )}
        <div className="actions">
          <button className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            ref={typeToConfirm ? undefined : firstFocus}
            className={`btn ${danger ? "btn-danger" : "btn-primary"}`}
            onClick={onConfirm}
            disabled={busy || !ready}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
