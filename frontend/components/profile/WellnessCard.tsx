"use client";

import { useState } from "react";
import { ApiError, api, errorMessage, type Wellness } from "@/lib/api";
import { ACTIVITY_LEVELS, CONTACT_PREFERENCES, DIETS, GOALS } from "@/lib/labels";
import { validateWellness, type Errors } from "@/lib/validation";
import { Field } from "./DemographicsCard";

type Form = {
  contact_preference: string;
  activity_level: string;
  diet_preference: string;
  sleep_goal_hours: string;
  allergies: string;
  lifestyle_notes: string;
  goals: string[];
};

const fromSection = (w: Wellness | null): Form => ({
  contact_preference: w?.contact_preference ?? "email",
  activity_level: w?.activity_level ?? "",
  diet_preference: w?.diet_preference ?? "",
  sleep_goal_hours: w?.sleep_goal_hours != null ? String(w.sleep_goal_hours) : "",
  allergies: w?.allergies ?? "",
  lifestyle_notes: w?.lifestyle_notes ?? "",
  goals: w?.goals ?? [],
});

export function WellnessCard({
  section,
  readOnly,
  onSaved,
}: {
  section: Wellness | null;
  readOnly: boolean;
  onSaved: (message: string) => void;
}) {
  const [form, setForm] = useState<Form>(fromSection(section));
  const [errors, setErrors] = useState<Errors>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const dirty = !section || JSON.stringify(form) !== JSON.stringify(fromSection(section));
  const toggleGoal = (code: string) =>
    set("goals", form.goals.includes(code) ? form.goals.filter((g) => g !== code) : [...form.goals, code]);

  async function save() {
    const found = validateWellness(form);
    setErrors(found);
    setGeneral(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      await api("/profiles/me/wellness/", {
        method: "PUT",
        body: { ...form, sleep_goal_hours: form.sleep_goal_hours === "" ? null : Number(form.sleep_goal_hours) },
      });
      onSaved("Wellness preferences saved");
    } catch (err) {
      if (err instanceof ApiError && Object.keys(err.fields).length) {
        setErrors(Object.fromEntries(Object.entries(err.fields).map(([k, v]) => [k, v[0]])));
      } else setGeneral(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card" id="wellness" aria-labelledby="well-title">
      <div className="section-head">
        <div>
          <h2 id="well-title">Wellness preferences and goals</h2>
          <p className="sub">Personal goals, not medical advice.</p>
        </div>
        {!section && <span className="badge off">Not saved yet</span>}
      </div>
      {general && (
        <div className="form-error" role="alert">
          {general}
        </div>
      )}
      <fieldset disabled={readOnly || saving} style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="field">
          <span className="label" id="w-contact-label">
            How should we contact you?
          </span>
          <div className="seg" role="group" aria-labelledby="w-contact-label">
            {CONTACT_PREFERENCES.map((c) => (
              <button key={c.value} type="button" className="seg-item" aria-pressed={form.contact_preference === c.value} onClick={() => set("contact_preference", c.value)}>
                {c.label}
              </button>
            ))}
          </div>
          {errors.contact_preference && <span className="error-text">{errors.contact_preference}</span>}
        </div>

        <div className="field">
          <span className="label" id="w-goals-label">
            Goals
          </span>
          <div className="seg" role="group" aria-labelledby="w-goals-label">
            {GOALS.map((g) => (
              <button key={g.value} type="button" className="chip" aria-pressed={form.goals.includes(g.value)} onClick={() => toggleGoal(g.value)}>
                {g.label}
              </button>
            ))}
          </div>
          {errors.goals && <span className="error-text">{errors.goals}</span>}
        </div>

        <div className="grid-3">
          <Field label="Activity level" id="w-activity" error={errors.activity_level}>
            <select id="w-activity" className="select" value={form.activity_level} onChange={(e) => set("activity_level", e.target.value)}>
              <option value="">Not set</option>
              {ACTIVITY_LEVELS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Diet" id="w-diet" error={errors.diet_preference}>
            <select id="w-diet" className="select" value={form.diet_preference} onChange={(e) => set("diet_preference", e.target.value)}>
              <option value="">Not set</option>
              {DIETS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Sleep goal (hours, 4–12)" id="w-sleep" error={errors.sleep_goal_hours}>
            <input id="w-sleep" type="number" min={4} max={12} className="input" value={form.sleep_goal_hours} onChange={(e) => set("sleep_goal_hours", e.target.value)} aria-invalid={!!errors.sleep_goal_hours} />
          </Field>
        </div>

        <Field label="Allergies (optional, private)" id="w-allergies" error={errors.allergies}>
          <textarea id="w-allergies" className="textarea" style={{ minHeight: 64 }} maxLength={500} value={form.allergies} onChange={(e) => set("allergies", e.target.value)} />
        </Field>
        <Field label="Lifestyle notes (optional, private)" id="w-notes" error={errors.lifestyle_notes}>
          <textarea id="w-notes" className="textarea" style={{ minHeight: 64 }} maxLength={500} value={form.lifestyle_notes} onChange={(e) => set("lifestyle_notes", e.target.value)} />
          <span className="hint">{form.lifestyle_notes.length}/500. Admins never see allergies or notes.</span>
        </Field>
      </fieldset>
      {!readOnly && (
        <div className="section-foot">
          <button className="btn btn-primary" onClick={save} disabled={saving || !dirty}>
            {saving ? "Saving…" : section ? "Save wellness" : "Create wellness"}
          </button>
        </div>
      )}
    </section>
  );
}
