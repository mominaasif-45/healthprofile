"use client";

import { useState } from "react";
import { ApiError, api, errorMessage, type Demographics } from "@/lib/api";
import { AGE_RANGES, GENDERS } from "@/lib/labels";
import { todayISO, validateDemographics, type Errors } from "@/lib/validation";

type Form = {
  full_name: string;
  preferred_name: string;
  date_of_birth: string;
  age_range: string;
  gender: string;
  city: string;
};

const fromSection = (d: Demographics | null, fallbackName: string): Form => ({
  full_name: d?.full_name ?? fallbackName,
  preferred_name: d?.preferred_name ?? "",
  date_of_birth: d?.date_of_birth ?? "",
  age_range: d?.age_range ?? "",
  gender: d?.gender ?? "",
  city: d?.city ?? "",
});

export function DemographicsCard({
  section,
  fallbackName,
  readOnly,
  onSaved,
}: {
  section: Demographics | null;
  fallbackName: string;
  readOnly: boolean;
  onSaved: (message: string) => void;
}) {
  const [form, setForm] = useState<Form>(fromSection(section, fallbackName));
  const [errors, setErrors] = useState<Errors>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (key: keyof Form, value: string) => setForm((f) => ({ ...f, [key]: value }));
  const dirty = JSON.stringify(form) !== JSON.stringify(fromSection(section, fallbackName)) || !section;

  async function save() {
    const found = validateDemographics(form);
    setErrors(found);
    setGeneral(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await api("/profiles/me/demographics/", {
        method: "PUT",
        body: { ...form, full_name: form.full_name.trim(), date_of_birth: form.date_of_birth || null, age_range: form.age_range || null },
      });
      onSaved("Demographics saved");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(Object.fromEntries(Object.entries(err.fields).map(([k, v]) => [k, v[0]])));
      } else setGeneral(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card" id="demographics" aria-labelledby="demo-title">
      <div className="section-head">
        <div>
          <h2 id="demo-title">Demographics</h2>
          <p className="sub">Fictional details only. Used to build your profile, not for diagnosis.</p>
        </div>
        {!section && <span className="badge off">Not saved yet</span>}
      </div>
      {general && (
        <div className="form-error" role="alert">
          {general}
        </div>
      )}
      <fieldset disabled={readOnly || saving} style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="grid-2">
          <Field label="Full name" id="d-full" error={errors.full_name}>
            <input id="d-full" className="input" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} aria-invalid={!!errors.full_name} />
          </Field>
          <Field label="Preferred name (optional)" id="d-pref" error={errors.preferred_name}>
            <input id="d-pref" className="input" value={form.preferred_name} onChange={(e) => set("preferred_name", e.target.value)} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Age range" id="d-age" error={errors.age_range}>
            <select id="d-age" className="select" value={form.age_range} onChange={(e) => set("age_range", e.target.value)} aria-invalid={!!errors.age_range}>
              <option value="">Select…</option>
              {AGE_RANGES.map((r) => (
                <option key={r} value={r}>
                  {r.replace("-", "–")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date of birth (optional)" id="d-dob" error={errors.date_of_birth}>
            <input id="d-dob" type="date" className="input" max={todayISO()} value={form.date_of_birth} onChange={(e) => set("date_of_birth", e.target.value)} aria-invalid={!!errors.date_of_birth} />
          </Field>
        </div>
        <div className="grid-2">
          <Field label="Gender (optional)" id="d-gender" error={errors.gender}>
            <select id="d-gender" className="select" value={form.gender} onChange={(e) => set("gender", e.target.value)}>
              <option value="">Prefer not to choose</option>
              {GENDERS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="City (optional)" id="d-city" error={errors.city}>
            <input id="d-city" className="input" value={form.city} onChange={(e) => set("city", e.target.value)} />
          </Field>
        </div>
      </fieldset>
      {!readOnly && (
        <div className="section-foot">
          <button className="btn btn-primary" onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving…" : section ? "Save demographics" : "Create demographics"}
          </button>
        </div>
      )}
    </section>
  );
}

export function Field({ label, id, error, children }: { label: string; id: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      {children}
      {error && (
        <span className="error-text" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
