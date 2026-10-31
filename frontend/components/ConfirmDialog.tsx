"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

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
  returnFocusFallback,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  typeToConfirm?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Where focus goes on close if the opening button can no longer take it (removed or disabled). */
  returnFocusFallback?: RefObject<HTMLElement | null>;
}) {
  const [typed, setTyped] = useState("");
  const firstFocus = useRef<HTMLInputElement & HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const ready = !typeToConfirm || typed.trim() === typeToConfirm;

  // Remember what had focus (the button that opened the dialog) and give it back on close.
  // If that button is gone or disabled by then, use returnFocusFallback instead.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const fallback = returnFocusFallback;
    firstFocus.current?.focus();
    return () => {
      const usable = opener && opener.isConnected && !(opener as HTMLButtonElement).disabled;
      (usable ? opener : fallback?.current)?.focus();
    };
  }, [returnFocusFallback]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
      if (e.key !== "Tab") return;
      // Keep Tab and Shift+Tab inside the dialog: wrap at either end.
      const items = dialogRef.current?.querySelectorAll<HTMLElement>("input, button");
      const focusable = Array.from(items ?? []).filter((el) => !(el as HTMLButtonElement).disabled);
      if (focusable.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (!dialogRef.current?.contains(active)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  // While busy both buttons are disabled, so keep focus on the dialog itself instead of letting it drop to the body.
  useEffect(() => {
    if (busy) dialogRef.current?.focus();
  }, [busy]);

  return (
    <div className="modal-back" role="presentation" onClick={() => !busy && onCancel()}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        tabIndex={-1}
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
          <button ref={typeToConfirm ? undefined : firstFocus} className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
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
