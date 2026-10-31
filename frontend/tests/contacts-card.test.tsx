import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EmergencyContact } from "@/lib/api";

// An in-memory stand-in for the backend: DELETE removes one contact; PATCH can answer with field errors.
const server = vi.hoisted(() => ({
  contacts: [] as EmergencyContact[],
  patchFields: null as Record<string, string[]> | null,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    api: vi.fn(async (path: string, opts: { method?: string } = {}) => {
      const id = Number(path.match(/emergency-contacts\/(\d+)\/$/)?.[1]);
      if (opts.method === "DELETE") server.contacts = server.contacts.filter((c) => c.id !== id);
      if (opts.method === "PATCH" && server.patchFields) {
        throw new actual.ApiError(400, "validation_error", "Invalid input.", server.patchFields);
      }
      return null;
    }),
  };
});

import { ContactsCard } from "@/components/profile/ContactsCard";

/** Stands in for the profile page: after a change it reloads the contacts, like afterChange() does. */
function Page() {
  const [contacts, setContacts] = useState(() => server.contacts.map((c) => ({ ...c })));
  async function afterChange() {
    await new Promise((r) => setTimeout(r, 10)); // the reload is a network round trip
    setContacts(server.contacts.map((c) => ({ ...c })));
  }
  return <ContactsCard contacts={contacts} readOnly={false} onChanged={afterChange} />;
}

function contact(id: number, name: string, is_primary = false): EmergencyContact {
  return { id, name, relationship: "friend", phone: "+92 300 0000000", is_primary };
}

describe("Contacts card focus after deleting", () => {
  beforeEach(() => {
    server.contacts = [];
    server.patchFields = null;
  });

  it("moves focus to the 'Emergency contacts' heading once the deleted contact's row is gone", async () => {
    server.contacts = [contact(1, "Ali Khan", true), contact(2, "Sana Rafiq")];
    const user = userEvent.setup();
    render(<Page />);

    const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(deleteButtons[1]);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Delete contact" }));

    await waitFor(() => expect(screen.queryByText("Sana Rafiq")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole("heading", { name: "Emergency contacts" })).toHaveFocus());
    expect(document.body).not.toHaveFocus();
  });
});

describe("Primary checkbox in the edit contact form", () => {
  const HINT = 'To change your primary contact, use "Make primary" on another contact.';

  beforeEach(() => {
    server.contacts = [contact(1, "Ali Khan", true), contact(2, "Sana Rafiq")];
    server.patchFields = null;
  });

  it("is ticked, disabled and explained when editing the current primary", async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getAllByRole("button", { name: "Edit" })[0]); // Ali Khan, the primary

    const box = screen.getByRole("checkbox", { name: "Make this my primary contact" });
    expect(box).toBeChecked();
    expect(box).toBeDisabled();
    expect(box).toHaveAccessibleDescription(HINT); // screen readers hear why it cannot be unticked
  });

  it("stays usable, with no hint, when editing a contact that is not primary", async () => {
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]); // Sana Rafiq

    const box = screen.getByRole("checkbox", { name: "Make this my primary contact" });
    expect(box).not.toBeChecked();
    expect(box).toBeEnabled();
    expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  });

  it("shows an is_primary error from the server under the checkbox", async () => {
    const message = 'You need a primary contact. To change it, choose "Make primary" on another contact.';
    server.patchFields = { is_primary: [message] };
    const user = userEvent.setup();
    render(<Page />);

    await user.click(screen.getAllByRole("button", { name: "Edit" })[1]);
    await user.click(screen.getByRole("button", { name: "Save contact" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("checkbox", { name: "Make this my primary contact" })).toHaveAccessibleDescription(message);
  });
});
