"use client";

import { useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ApiError, api, errorMessage, type EmergencyContact } from "@/lib/api";
import { RELATIONSHIPS, labelOf } from "@/lib/labels";
import { validateContact, type Errors } from "@/lib/validation";
import { Field } from "./DemographicsCard";

const MAX_CONTACTS = 3;
type Form = { name: string; relationship: string; phone: string; is_primary: boolean };
const blank: Form = { name: "", relationship: "", phone: "", is_primary: false };

export function ContactsCard({
  contacts,
  readOnly,
  onChanged,
}: {
  contacts: EmergencyContact[];
  readOnly: boolean;
  onChanged: (message: string) => void | Promise<void>;
}) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const [form, setForm] = useState<Form>(blank);
  const [errors, setErrors] = useState<Errors>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toDelete, setToDelete] = useState<EmergencyContact | null>(null);
  // Always rendered, so focus has somewhere to go when the deleted contact's row disappears.
  const heading = useRef<HTMLHeadingElement>(null);
  // Bumped after a delete and reload; the effect below moves focus once the new list has rendered.
  const [refocus, setRefocus] = useState(0);

  useEffect(() => {
    if (refocus > 0) heading.current?.focus();
  }, [refocus]);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));

  function open(contact?: EmergencyContact) {
    setErrors({});
    setGeneral(null);
    setEditing(contact ? contact.id : "new");
    setForm(contact ? { name: contact.name, relationship: contact.relationship, phone: contact.phone, is_primary: contact.is_primary } : blank);
  }

  async function run(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setGeneral(null);
    try {
      await action();
      setEditing(null);
      onChanged(message);
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(Object.fromEntries(Object.entries(err.fields).map(([k, v]) => [k, v[0]])));
        if (err.fields.emergency_contacts) setGeneral(err.fields.emergency_contacts[0]);
      } else setGeneral(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    const found = validateContact(form);
    setErrors(found);
    if (Object.keys(found).length) return;
    const body = { ...form, name: form.name.trim(), phone: form.phone.trim() };
    if (editing === "new") await run(() => api("/profiles/me/emergency-contacts/", { method: "POST", body }), "Contact added");
    else await run(() => api(`/profiles/me/emergency-contacts/${editing}/`, { method: "PATCH", body }), "Contact updated");
  }

  async function remove() {
    if (!toDelete) return;
    setBusy(true);
    try {
      await api(`/profiles/me/emergency-contacts/${toDelete.id}/`, { method: "DELETE" });
      setToDelete(null);
      await onChanged("Contact deleted");
      setRefocus((n) => n + 1); // the row's Delete button is gone after the reload
    } catch (err) {
      setToDelete(null);
      setGeneral(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const full = contacts.length >= MAX_CONTACTS;

  return (
    <section className="card" id="contacts" aria-labelledby="contacts-title">
      <div className="section-head">
        <div>
          <h2 id="contacts-title" ref={heading} tabIndex={-1}>
            Emergency contacts
          </h2>
          <p className="sub">Up to {MAX_CONTACTS} people. One is marked primary.</p>
        </div>
        {!readOnly && editing === null && (
          <button className="btn btn-sm" onClick={() => open()} disabled={full} title={full ? "You have reached the limit of 3 contacts" : undefined}>
            + Add contact
          </button>
        )}
      </div>
      {general && (
        <div className="form-error" role="alert">
          {general}
        </div>
      )}

      {contacts.length === 0 && editing !== "new" && <p className="muted">No emergency contacts yet.</p>}
      <div className="contact-list">
        {contacts.map((c) =>
          editing === c.id ? null : (
            <div key={c.id} className="contact-card">
              <div>
                <strong>
                  {c.name} {c.is_primary && <span className="badge">Primary</span>}
                </strong>
                <small>
                  {labelOf(RELATIONSHIPS, c.relationship)} · {c.phone}
                </small>
              </div>
              {!readOnly && (
                <div className="contact-actions">
                  {!c.is_primary && (
                    <button className="btn btn-sm" disabled={busy} onClick={() => run(() => api(`/profiles/me/emergency-contacts/${c.id}/`, { method: "PATCH", body: { is_primary: true } }), "Primary contact changed")}>
                      Make primary
                    </button>
                  )}
                  <button className="btn btn-sm" onClick={() => open(c)}>
                    Edit
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={() => setToDelete(c)}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          )
        )}
      </div>

      {editing !== null && (
        <div className="contact-form" role="group" aria-label={editing === "new" ? "Add contact" : "Edit contact"}>
          <div className="grid-2">
            <Field label="Name" id="c-name" error={errors.name}>
              <input id="c-name" className="input" value={form.name} onChange={(e) => set("name", e.target.value)} aria-invalid={!!errors.name} />
            </Field>
            <Field label="Relationship" id="c-rel" error={errors.relationship}>
              <select id="c-rel" className="select" value={form.relationship} onChange={(e) => set("relationship", e.target.value)} aria-invalid={!!errors.relationship}>
                <option value="">Select…</option>
                {RELATIONSHIPS.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Phone (fictional)" id="c-phone" error={errors.phone}>
            <input id="c-phone" type="tel" className="input" placeholder="+92 300 0000000" value={form.phone} onChange={(e) => set("phone", e.target.value)} aria-invalid={!!errors.phone} />
          </Field>
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
            <input type="checkbox" checked={form.is_primary} onChange={(e) => set("is_primary", e.target.checked)} />
            Make this my primary contact
          </label>
          <div className="section-foot">
            <button className="btn" onClick={() => setEditing(null)} disabled={busy}>
              Cancel
            </button>
            <button className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "Saving…" : editing === "new" ? "Add contact" : "Save contact"}
            </button>
          </div>
        </div>
      )}

      {toDelete && (
        <ConfirmDialog title="Delete this contact?" confirmLabel="Delete contact" busy={busy} onConfirm={remove} onCancel={() => setToDelete(null)} returnFocusFallback={heading}>
          {toDelete.name} will be removed from your profile.
          {toDelete.is_primary && contacts.length > 1 && " Your oldest remaining contact becomes primary."}
        </ConfirmDialog>
      )}
    </section>
  );
}
