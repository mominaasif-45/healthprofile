import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EmergencyContact } from "@/lib/api";

// An in-memory stand-in for the backend: DELETE removes one contact.
const server = vi.hoisted(() => ({ contacts: [] as EmergencyContact[] }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: vi.fn(async (path: string, opts: { method?: string } = {}) => {
    const id = Number(path.match(/emergency-contacts\/(\d+)\/$/)?.[1]);
    if (opts.method === "DELETE") server.contacts = server.contacts.filter((c) => c.id !== id);
    return null;
  }),
}));

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
