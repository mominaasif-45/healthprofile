import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { ConfirmDialog } from "@/components/ConfirmDialog";

type HarnessProps = { typeToConfirm?: string; disableOpenerOnClose?: boolean };

/** A page with an opener button, a fallback heading, and the dialog, wired up like the admin page. */
function Harness({ typeToConfirm, disableOpenerOnClose = false }: HarnessProps) {
  const [open, setOpen] = useState(false);
  // Confirming starts a request that never finishes, so the dialog stays busy, like a slow network.
  const [busy, setBusy] = useState(false);
  const [openerDisabled, setOpenerDisabled] = useState(false);
  const fallback = useRef<HTMLHeadingElement>(null);

  function close() {
    if (disableOpenerOnClose) setOpenerDisabled(true);
    setOpen(false);
  }

  return (
    <>
      <h1 ref={fallback} tabIndex={-1}>
        Page heading
      </h1>
      <button onClick={() => setOpen(true)} disabled={openerDisabled}>
        Open dialog
      </button>
      {open && (
        <ConfirmDialog
          title="Deactivate this profile?"
          confirmLabel="Deactivate"
          busy={busy}
          typeToConfirm={typeToConfirm}
          onConfirm={() => setBusy(true)}
          onCancel={close}
          returnFocusFallback={fallback}
        >
          Body text
        </ConfirmDialog>
      )}
    </>
  );
}

async function openDialog(props: HarnessProps = {}) {
  const user = userEvent.setup();
  render(<Harness {...props} />);
  await user.click(screen.getByRole("button", { name: "Open dialog" }));
  return user;
}

describe("ConfirmDialog keyboard behaviour", () => {
  it("puts focus on Cancel when it opens without a text box", async () => {
    await openDialog();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });

  it("puts focus on the type-to-confirm box when there is one", async () => {
    await openDialog({ typeToConfirm: "DELETE" });
    expect(screen.getByRole("textbox", { name: /Type DELETE to confirm/ })).toHaveFocus();
  });

  it("keeps Tab and Shift+Tab inside the dialog, wrapping at both ends", async () => {
    const user = await openDialog();
    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Deactivate" });

    await user.tab();
    expect(confirm).toHaveFocus();
    await user.tab(); // past the last button, back to the first
    expect(cancel).toHaveFocus();
    await user.tab({ shift: true }); // before the first button, round to the last
    expect(confirm).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
  });

  it("closes on Escape and gives focus back to the button that opened it", async () => {
    const user = await openDialog();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open dialog" })).toHaveFocus();
  });

  it("keeps focus on the dialog box while busy and ignores Escape", async () => {
    const user = await openDialog();
    await user.tab();
    await user.keyboard("{Enter}"); // confirm: both buttons are now disabled
    const dialog = screen.getByRole("dialog");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(dialog).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(dialog).toHaveFocus();
  });

  it("falls back to the given element when the opener is disabled on close", async () => {
    const user = await openDialog({ disableOpenerOnClose: true });
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Page heading" })).toHaveFocus();
  });
});
