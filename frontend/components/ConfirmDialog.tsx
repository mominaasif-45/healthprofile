"use client";

import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";

type Props = {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  busyLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  /** Where focus goes on close if the opening button can no longer take it (e.g. it is now disabled). */
  returnFocusFallback?: RefObject<HTMLElement | null>;
};

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal confirmation dialog with keyboard support: focus moves in on open (to Cancel, the safe choice,
 * so pressing Enter straight away never confirms),
 * Tab / Shift+Tab stay inside, Escape cancels (unless busy), and focus goes
 * back to the button that opened it on close.
 */
export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  busyLabel,
  busy,
  onConfirm,
  onCancel,
  returnFocusFallback,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  // The element that had focus when the dialog mounted, i.e. the button that opened it.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);
  const busyRef = useRef(busy);
  const cancelRef = useRef(onCancel);

  useEffect(() => {
    busyRef.current = busy;
    cancelRef.current = onCancel;
  });

  // One effect so the order is fixed: on open, attach the key and focus guards, then move focus in;
  // on close, remove the guards first, then give focus back to the opener.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    function focusInside() {
      if (!dialog) return;
      const safe = cancelButtonRef.current;
      const target = safe && !safe.disabled ? safe : dialog;
      target.focus();
      // Belt and braces: if the browser refused (e.g. the button could not take focus), use the dialog box.
      if (!dialog.contains(document.activeElement)) dialog.focus();
    }

    // Capture phase: runs before any other handler on the page can swallow Tab or Escape.
    function onKeyDown(e: KeyboardEvent) {
      if (!dialog) return;
      if (e.key === "Escape") {
        e.preventDefault();
        if (!busyRef.current) cancelRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      e.preventDefault();
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        dialog.focus();
        return;
      }
      const at = items.indexOf(document.activeElement as HTMLElement);
      const next = e.shiftKey ? (at <= 0 ? items.length - 1 : at - 1) : at === -1 || at === items.length - 1 ? 0 : at + 1;
      items[next].focus();
    }

    // If focus ever lands outside the dialog while it is open, pull it back in.
    function onFocusIn(e: FocusEvent) {
      if (dialog && !dialog.contains(e.target as Node)) focusInside();
    }

    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", onFocusIn, true);
    focusInside();

    const fallback = returnFocusFallback;
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", onFocusIn, true);
      const usable = opener && opener.isConnected && !(opener as HTMLButtonElement).disabled;
      (usable ? opener : fallback?.current)?.focus();
    };
  }, [opener, returnFocusFallback]);

  // While busy both buttons are disabled, so keep focus on the dialog itself.
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
        aria-labelledby="dlg-title"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="dlg-title">{title}</h2>
        <p className="muted">{children}</p>
        <div className="actions">
          <button ref={cancelButtonRef} className="btn" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
