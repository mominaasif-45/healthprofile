"use client";

import { useState } from "react";
import { ApiError, api, errorMessage, type NoShowRequest, type NoShowResponse } from "@/lib/api";
import { Field } from "./DemographicsCard";

/**
 * Educational demo: the model's chance that a FICTIONAL appointment is missed.
 * Never reads or sends profile data. "Not recorded" (an empty select / empty number box) is sent as null.
 * Quick checks mirror the server's rules; the server stays the final judge and its field errors are shown too.
 */

const PATH = "/ml/v1/no-show/predict/";
const NOT_RECORDED = "";

type Option = { value: string; label: string };
const WEEKDAYS: Option[] = [
  { value: "mon", label: "Monday" },
  { value: "tue", label: "Tuesday" },
  { value: "wed", label: "Wednesday" },
  { value: "thu", label: "Thursday" },
  { value: "fri", label: "Friday" },
  { value: "sat", label: "Saturday" },
];
const HOURS: Option[] = Array.from({ length: 10 }, (_, i) => ({ value: String(8 + i), label: `${8 + i}:00` }));
const VISIT_TYPES: Option[] = [
  { value: "new_visit", label: "New visit" },
  { value: "follow_up", label: "Follow-up" },
  { value: "routine_checkup", label: "Routine check-up" },
  { value: "wellness_class", label: "Wellness class" },
];
const CHANNELS: Option[] = [
  { value: "online", label: "Online" },
  { value: "phone", label: "Phone" },
  { value: "in_person", label: "In person" },
];
const REMINDERS: Option[] = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];
const DISTANCES: Option[] = [
  { value: "under_5km", label: "Under 5 km" },
  { value: "5_15km", label: "5–15 km" },
  { value: "15_30km", label: "15–30 km" },
  { value: "over_30km", label: "Over 30 km" },
];
const AGE_BANDS: Option[] = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"].map((v) => ({
  value: v,
  label: v.replace("-", "–"),
}));

type Form = Record<keyof NoShowRequest, string>;
type Errors = Partial<Record<keyof NoShowRequest, string>>;

// The same fictional appointment as the first Swagger example, so the two can be compared.
const EXAMPLE: Form = {
  lead_time_days: "21",
  weekday: "mon",
  hour: "9",
  visit_type: "new_visit",
  booking_channel: "online",
  reminder_sent: "no",
  prior_visits: "3",
  prior_no_shows: "1",
  distance_band: "15_30km",
  age_band: NOT_RECORDED,
};

/** A whole number from 0 to max, null for an empty box, or undefined when invalid. */
function wholeNumber(text: string, max: number): number | null | undefined {
  if (text.trim() === "") return null;
  if (!/^\d+$/.test(text.trim())) return undefined;
  const n = Number(text);
  return n <= max ? n : undefined;
}

/** The server's rules, checked before sending. Returns the request body only when everything is valid. */
function check(form: Form): { errors: Errors; body: NoShowRequest | null } {
  const errors: Errors = {};
  const lead = wholeNumber(form.lead_time_days, 90);
  if (lead === undefined || lead === null) errors.lead_time_days = "Enter a whole number from 0 to 90.";
  const visits = wholeNumber(form.prior_visits, 20);
  if (visits === undefined) errors.prior_visits = "Enter a whole number from 0 to 20.";
  const noShows = wholeNumber(form.prior_no_shows, 20);
  if (noShows === undefined) errors.prior_no_shows = "Enter a whole number from 0 to 20.";
  if (visits !== undefined && noShows !== undefined) {
    if ((visits === null) !== (noShows === null)) {
      errors.prior_no_shows = "Fill in both earlier fields, or leave both empty.";
    } else if (visits !== null && noShows !== null && noShows > visits) {
      errors.prior_no_shows = "Can't be more than earlier appointments.";
    }
  }
  if (Object.keys(errors).length) return { errors, body: null };
  const blankable = (v: string) => (v === NOT_RECORDED ? null : v);
  return {
    errors,
    body: {
      lead_time_days: lead as number,
      weekday: form.weekday,
      hour: Number(form.hour),
      visit_type: form.visit_type,
      booking_channel: form.booking_channel,
      reminder_sent: blankable(form.reminder_sent),
      prior_visits: visits as number | null,
      prior_no_shows: noShows as number | null,
      distance_band: blankable(form.distance_band),
      age_band: blankable(form.age_band),
    },
  };
}

/** 0.5279 -> "52.8%", 0.22 -> "22%". Rounds via whole basis points to avoid floating-point surprises. */
function percentValue(p: number): number {
  return Math.round(Math.round(p * 10000) / 10) / 10;
}
const percent = (p: number) => `${percentValue(p)}%`;

type Problem = { text: string; signIn?: boolean };
function problemFor(err: unknown): Problem {
  if (err instanceof ApiError) {
    if (err.status === 401) return { text: "Your session has ended. Please sign in again.", signIn: true };
    if (err.status === 403) return { text: "Your request was blocked for security reasons. Reload the page and try again." };
    if (err.status === 429) return { text: "That's a lot of checks in a short time. Please wait a minute and try again." };
    if (err.status === 503) return { text: "The demo model is unavailable right now. Please try again later." };
  }
  return { text: errorMessage(err) };
}

export function NoShowDemoCard() {
  const [form, setForm] = useState<Form>(EXAMPLE);
  const [errors, setErrors] = useState<Errors>({});
  const [problem, setProblem] = useState<Problem | null>(null);
  const [result, setResult] = useState<NoShowResponse | null>(null);
  const [busy, setBusy] = useState(false);

  // Any change makes the old answer stale, so it is cleared rather than shown next to different inputs.
  const set = (key: keyof Form, value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setResult(null);
    setProblem(null);
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const checked = check(form);
    setErrors(checked.errors);
    setProblem(null);
    setResult(null);
    if (!checked.body) return;
    setBusy(true);
    try {
      setResult(await api<NoShowResponse>(PATH, { method: "POST", body: checked.body }));
    } catch (err) {
      const known = err instanceof ApiError && err.status === 400
        ? Object.entries(err.fields).filter(([k]) => k in EXAMPLE)
        : [];
      if (known.length) setErrors(Object.fromEntries(known.map(([k, v]) => [k, v[0]])));
      else setProblem(problemFor(err));
    } finally {
      setBusy(false);
    }
  }

  const select = (key: keyof Form, id: string, label: string, options: Option[], blank = false) => (
    <Field label={label} id={id} error={errors[key]}>
      <select id={id} className="select" value={form[key]} onChange={(e) => set(key, e.target.value)} aria-invalid={!!errors[key]}>
        {blank && <option value={NOT_RECORDED}>Not recorded</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );

  const number = (key: keyof Form, id: string, label: string, max: number, hint?: string) => (
    <Field label={label} id={id} error={errors[key]}>
      <input id={id} type="number" inputMode="numeric" min={0} max={max} step={1} className="input" value={form[key]}
        onChange={(e) => set(key, e.target.value)} aria-invalid={!!errors[key]} />
      {hint && <span className="hint">{hint}</span>}
    </Field>
  );

  const above = result ? result.probability >= result.threshold : false;

  return (
    <section className="card" id="no-show-demo" aria-labelledby="ns-title">
      <div className="section-head">
        <div>
          <h2 id="ns-title">No-show likelihood demo</h2>
          <p className="sub">A fictional appointment. Change any value and check again.</p>
        </div>
        <span className="badge">Demo</span>
      </div>

      <p style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px", fontSize: 13, margin: "0 0 14px" }}>
        <strong>Educational demo.</strong> This model was trained on made-up appointments. It is not medical advice or a
        diagnosis, and it says nothing about you: it never uses your profile.
      </p>

      {problem && (
        <div className="form-error" role="alert">
          <span>{problem.text}</span>
          {problem.signIn && (
            <>
              {" "}
              <a href="/login">Sign in again</a>
            </>
          )}
        </div>
      )}

      <form onSubmit={submit} noValidate>
        <div className="grid-3">
          {number("lead_time_days", "ns-lead", "Days between booking and appointment", 90)}
          {select("weekday", "ns-day", "Day", WEEKDAYS)}
          {select("hour", "ns-hour", "Start time", HOURS)}
        </div>
        <div className="grid-3">
          {select("visit_type", "ns-visit", "Visit type", VISIT_TYPES)}
          {select("booking_channel", "ns-channel", "Booked by", CHANNELS)}
          {select("reminder_sent", "ns-reminder", "Reminder sent", REMINDERS, true)}
        </div>
        <div className="grid-3">
          {number("prior_visits", "ns-visits", "Earlier appointments", 20, "Leave empty if not recorded.")}
          {number("prior_no_shows", "ns-missed", "Earlier missed appointments", 20, "Leave empty if not recorded.")}
          {select("distance_band", "ns-distance", "Travel distance", DISTANCES, true)}
        </div>
        <div className="grid-3">{select("age_band", "ns-age", "Age group", AGE_BANDS, true)}</div>
        <div className="section-foot">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Checking…" : "Check this example"}
          </button>
        </div>
      </form>

      <div role="region" aria-label="Demo result" aria-live="polite">
        {result && (
          <div style={{ marginTop: 14 }}>
            <p style={{ fontSize: 20, fontWeight: 700, margin: "0 0 8px" }}>
              {`${percent(result.probability)} chance this fictional appointment is missed`}
            </p>
            <div role="meter" aria-label="Chance of a missed appointment" aria-valuenow={percentValue(result.probability)}
              aria-valuemin={0} aria-valuemax={100}
              style={{ height: 8, borderRadius: 8, background: "var(--border-strong)", overflow: "hidden", margin: "0 0 10px" }}>
              <i style={{ display: "block", height: "100%", width: percent(result.probability), background: "var(--primary)" }} />
            </div>
            <p style={{ margin: "0 0 8px" }}>
              {above ? (
                <>
                  Above the {percent(result.threshold)} line, so the demo flags it as <strong>likely to be missed</strong>.
                </>
              ) : (
                <>
                  Below the {percent(result.threshold)} line, so the demo marks it as <strong>likely to be attended</strong>.
                </>
              )}
            </p>
            <p className="hint" style={{ margin: 0 }}>
              <span>Model {result.model_version}</span> · <span>{result.disclaimer}</span>
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
