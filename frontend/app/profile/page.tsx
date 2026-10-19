"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { IconClock, IconLock, IconShield, IconTarget, IconUser } from "@/components/Icons";
import { Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ApiError, api, errorMessage, minutesUntilRenewal, userLogout, type Profile, type User } from "@/lib/api";
import { dateTime, greeting } from "@/lib/format";

const AGE_RANGES = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"];
const CONTACTS: { value: "email" | "phone" | "sms"; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "sms", label: "SMS" },
];
const SUGGESTED = ["Sleep 7+ hours", "Walk 8,000 steps", "Reduce stress", "More vegetables"];

type Form = {
  full_name: string;
  date_of_birth: string;
  age_range: string;
  contact_preference: "email" | "phone" | "sms";
  wellness_goals: string[];
  lifestyle_notes: string;
  allergies: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
};

const emptyForm = (name = ""): Form => ({
  full_name: name,
  date_of_birth: "",
  age_range: "",
  contact_preference: "email",
  wellness_goals: [],
  lifestyle_notes: "",
  allergies: "",
  emergency_contact_name: "",
  emergency_contact_phone: "",
});

const fromProfile = (p: Profile): Form => ({
  full_name: p.full_name,
  date_of_birth: p.date_of_birth ?? "",
  age_range: p.age_range ?? "",
  contact_preference: p.contact_preference,
  wellness_goals: p.wellness_goals,
  lifestyle_notes: p.lifestyle_notes,
  allergies: p.allergies,
  emergency_contact_name: p.emergency_contact_name,
  emergency_contact_phone: p.emergency_contact_phone,
});

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<Form>(emptyForm());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [addingGoal, setAddingGoal] = useState(false);
  const [newGoal, setNewGoal] = useState("");
  const [renews, setRenews] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const me = await api<User>("/auth/me/");
      setUser(me);
      try {
        const p = await api<Profile>("/profiles/me/");
        setProfile(p);
        setForm(fromProfile(p));
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) setForm(emptyForm(me.name));
        else throw err;
      }
      setLoading(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      else {
        setError(err);
        setLoading(false);
      }
    }
  }, [router]);

  // Fetching on mount is the intended use of an effect here; load() only sets state after awaiting the API.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRenews(minutesUntilRenewal());
    const t = setInterval(() => setRenews(minutesUntilRenewal()), 30000);
    return () => clearInterval(t);
  }, [profile]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  const deactivated = profile?.status === "deactivated";
  const isNew = !profile;
  const dirty = useMemo(
    () => (profile ? JSON.stringify(form) !== JSON.stringify(fromProfile(profile)) : true),
    [form, profile]
  );

  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm((f) => ({ ...f, [key]: value }));
  const fieldErr = (name: string) => (error instanceof ApiError ? error.fields[name]?.[0] : undefined);

  function toggleGoal(goal: string) {
    set(
      "wellness_goals",
      form.wellness_goals.includes(goal)
        ? form.wellness_goals.filter((g) => g !== goal)
        : [...form.wellness_goals, goal]
    );
  }

  function addGoal() {
    const g = newGoal.trim();
    if (g && !form.wellness_goals.some((x) => x.toLowerCase() === g.toLowerCase())) {
      set("wellness_goals", [...form.wellness_goals, g]);
    }
    setNewGoal("");
    setAddingGoal(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    const body = {
      ...form,
      date_of_birth: form.date_of_birth || null,
      age_range: form.age_range || null,
    };
    try {
      const saved = isNew
        ? await api<Profile>("/profiles/me/", { method: "POST", body })
        : await api<Profile>("/profiles/me/", { method: "PATCH", body });
      setProfile(saved);
      setForm(fromProfile(saved));
      setToast(isNew ? "Profile created" : "Changes saved");
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  async function signOut() {
    await userLogout().catch(() => {});
    router.replace("/login");
  }

  const goalOptions = [...SUGGESTED, ...form.wellness_goals.filter((g) => !SUGGESTED.includes(g))];
  const firstName = (user?.name ?? "").split(" ")[0];
  const generalError =
    error && !(error instanceof ApiError && Object.keys(error.fields).length > 0) ? errorMessage(error) : null;

  if (loading) {
    return (
      <div className="main" style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="skeleton" style={{ width: 200, height: 28, marginBottom: 20 }} />
        <div className="skeleton" style={{ height: 220 }} />
      </div>
    );
  }

  return (
    <Shell
      nav={[
        { href: "#profile", label: "My profile", icon: <IconUser />, current: true },
        { href: "#goals", label: "Wellness goals", icon: <IconTarget /> },
        { href: "#privacy", label: "Privacy and security", icon: <IconShield /> },
      ]}
      box={
        <>
          <strong>Demo environment</strong>
          Every profile here is synthetic. No real patient data.
        </>
      }
      onSignOut={signOut}
    >
      <header className="page-head" id="profile">
        <div>
          <span className="eyebrow">My profile</span>
          <h1>
            {greeting()}, {firstName}
          </h1>
          <p>Keep your wellness profile up to date. Only you and clinic admins can see it.</p>
        </div>
        <div className="actions">
          <ThemeToggle />
          <button
            className="btn"
            onClick={() => {
              setError(null);
              setForm(profile ? fromProfile(profile) : emptyForm(user?.name));
            }}
            disabled={saving || !dirty}
          >
            Cancel
          </button>
          <button className="btn btn-primary" onClick={save} disabled={saving || deactivated || !dirty}>
            {saving ? "Saving…" : isNew ? "Create profile" : "Save changes"}
          </button>
        </div>
      </header>

      {deactivated && (
        <div className="form-error" role="status">
          This profile has been deactivated by an administrator and can no longer be edited.
        </div>
      )}
      {isNew && (
        <div className="info-box" role="status">
          <span>
            Welcome! Fill in your details below and choose <strong>Create profile</strong> to save.
          </span>
        </div>
      )}
      {generalError && (
        <div className="form-error" role="alert">
          {generalError}
        </div>
      )}

      <div className="content-grid">
        <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }} disabled={deactivated}>
          <section className="card">
            <h2>Personal details</h2>
            <div className="grid-2" style={{ marginTop: 14 }}>
              <div className="field">
                <label className="label" htmlFor="full_name">
                  Full name
                </label>
                <input
                  id="full_name"
                  className="input"
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                  aria-invalid={!!fieldErr("full_name")}
                />
                {fieldErr("full_name") && <span className="error-text">{fieldErr("full_name")}</span>}
              </div>
              <div className="field">
                <label className="label" htmlFor="age_range">
                  Age range
                </label>
                <select
                  id="age_range"
                  className="select"
                  value={form.age_range}
                  onChange={(e) => set("age_range", e.target.value)}
                  aria-invalid={!!fieldErr("age_range")}
                >
                  <option value="">Select…</option>
                  {AGE_RANGES.map((r) => (
                    <option key={r} value={r}>
                      {r.replace("-", "–")}
                    </option>
                  ))}
                </select>
                {fieldErr("age_range") && <span className="error-text">{fieldErr("age_range")}</span>}
              </div>
            </div>
            <div className="grid-2">
              <div className="field">
                <label className="label" htmlFor="dob">
                  Date of birth (optional)
                </label>
                <input
                  id="dob"
                  type="date"
                  className="input"
                  value={form.date_of_birth}
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => set("date_of_birth", e.target.value)}
                  aria-invalid={!!fieldErr("date_of_birth")}
                />
                {fieldErr("date_of_birth") && <span className="error-text">{fieldErr("date_of_birth")}</span>}
              </div>
              <div className="field">
                <span className="label" id="contact-label">
                  Contact preference
                </span>
                <div className="seg" role="group" aria-labelledby="contact-label">
                  {CONTACTS.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      className="seg-item"
                      aria-pressed={form.contact_preference === c.value}
                      onClick={() => set("contact_preference", c.value)}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
                {fieldErr("contact_preference") && <span className="error-text">{fieldErr("contact_preference")}</span>}
              </div>
            </div>
          </section>

          <section className="card" id="goals">
            <h2>Wellness goals</h2>
            <p className="sub">Pick what you are working on. These are personal goals, not medical advice.</p>
            <div className="seg">
              {goalOptions.map((g) => (
                <button
                  key={g}
                  type="button"
                  className="chip"
                  aria-pressed={form.wellness_goals.includes(g)}
                  onClick={() => toggleGoal(g)}
                >
                  {g}
                </button>
              ))}
              {!addingGoal && (
                <button type="button" className="chip chip-add" onClick={() => setAddingGoal(true)}>
                  + Add goal
                </button>
              )}
            </div>
            {addingGoal && (
              <div className="goal-input">
                <input
                  className="input"
                  autoFocus
                  placeholder="e.g. Stretch every morning"
                  maxLength={60}
                  value={newGoal}
                  onChange={(e) => setNewGoal(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addGoal();
                    }
                    if (e.key === "Escape") setAddingGoal(false);
                  }}
                  aria-label="New goal"
                />
                <button type="button" className="btn btn-sm" onClick={addGoal}>
                  Add
                </button>
              </div>
            )}
            {fieldErr("wellness_goals") && <p className="error-text">{fieldErr("wellness_goals")}</p>}
            <div className="field" style={{ marginTop: 18, marginBottom: 0 }}>
              <label className="label" htmlFor="notes">
                Lifestyle notes (optional)
              </label>
              <textarea
                id="notes"
                className="textarea"
                maxLength={1000}
                value={form.lifestyle_notes}
                onChange={(e) => set("lifestyle_notes", e.target.value)}
                aria-invalid={!!fieldErr("lifestyle_notes")}
              />
              {fieldErr("lifestyle_notes") && <span className="error-text">{fieldErr("lifestyle_notes")}</span>}
            </div>
          </section>

          <section className="card">
            <h2>Allergies and emergency contact</h2>
            <div className="grid-3" style={{ marginTop: 14 }}>
              <div className="field">
                <label className="label" htmlFor="allergies">
                  Allergies (optional)
                </label>
                <input
                  id="allergies"
                  className="input"
                  maxLength={500}
                  value={form.allergies}
                  onChange={(e) => set("allergies", e.target.value)}
                  aria-invalid={!!fieldErr("allergies")}
                />
                {fieldErr("allergies") && <span className="error-text">{fieldErr("allergies")}</span>}
              </div>
              <div className="field">
                <label className="label" htmlFor="ename">
                  Emergency contact
                </label>
                <input
                  id="ename"
                  className="input"
                  value={form.emergency_contact_name}
                  onChange={(e) => set("emergency_contact_name", e.target.value)}
                  aria-invalid={!!fieldErr("emergency_contact_name")}
                />
                {fieldErr("emergency_contact_name") && (
                  <span className="error-text">{fieldErr("emergency_contact_name")}</span>
                )}
              </div>
              <div className="field">
                <label className="label" htmlFor="ephone">
                  Contact phone
                </label>
                <input
                  id="ephone"
                  type="tel"
                  className="input"
                  placeholder="+92 300 0000000"
                  value={form.emergency_contact_phone}
                  onChange={(e) => set("emergency_contact_phone", e.target.value)}
                  aria-invalid={!!fieldErr("emergency_contact_phone")}
                />
                {fieldErr("emergency_contact_phone") && (
                  <span className="error-text">{fieldErr("emergency_contact_phone")}</span>
                )}
              </div>
            </div>
          </section>
        </fieldset>

        <aside className="aside">
          <section className="hero-card" aria-label="Profile strength">
            <div className="row">
              <strong>Profile strength</strong>
              <span className="badge">{profile ? (deactivated ? "Deactivated" : "Active") : "Draft"}</span>
            </div>
            <div className="big">{profile?.completeness.percent ?? 0}%</div>
            <div className="bar" role="progressbar" aria-valuenow={profile?.completeness.percent ?? 0} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: `${profile?.completeness.percent ?? 0}%` }} />
            </div>
            <p className="hint">
              {profile
                ? profile.completeness.missing[0]
                  ? `${profile.completeness.missing[0]} to complete your profile.`
                  : "Your profile is complete. Nice work."
                : "Create your profile to see your strength."}
            </p>
          </section>

          <section className="card" id="privacy">
            <h2 style={{ fontSize: 15 }}>Your session</h2>
            <div className="list-row">
              <span className="icon-tile">
                <IconLock size={16} />
              </span>
              <div>
                <strong style={{ fontSize: 13 }}>Signed in securely</strong>
                <small>Token kept in an HttpOnly cookie</small>
              </div>
            </div>
            <div className="list-row">
              <span className="icon-tile">
                <IconClock size={16} />
              </span>
              <div>
                <strong style={{ fontSize: 13 }}>
                  {renews === null ? "Renews automatically" : renews === 0 ? "Renews on next request" : `Renews in ${renews} min`}
                </strong>
                <small>{profile ? `Last updated ${dateTime(profile.updated_at)}` : "No profile saved yet"}</small>
              </div>
            </div>
          </section>
        </aside>
      </div>

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </Shell>
  );
}
