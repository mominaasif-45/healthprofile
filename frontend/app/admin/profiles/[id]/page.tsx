"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AdminBox, adminNav } from "@/components/AdminChrome";
import { CompletionBadge, CompletionBar } from "@/components/Completion";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { IconArrowLeft } from "@/components/Icons";
import { Initials, Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ApiError, api, errorMessage, type AdminAuditEvent, type AdminProfile, type Page } from "@/lib/api";
import { dateShort, dateTime, ageLabel } from "@/lib/format";
import { ACTIVITY_LEVELS, CONTACT_PREFERENCES, DIETS, GENDERS, GOALS, RELATIONSHIPS, actionLabel, labelOf } from "@/lib/labels";
import { useAdmin } from "@/lib/useAdmin";

const goalLabel = (code: string) => GOALS.find((g) => g.value === code)?.label ?? code;

export default function AdminProfileDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { admin, signOut, handleSessionError } = useAdmin();
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [history, setHistory] = useState<AdminAuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<"deactivate" | "reactivate" | null>(null);
  const [busy, setBusy] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      const res = await api<Page<AdminAuditEvent>>(`/admin/profiles/${id}/audit-events/`, { auth: "admin" });
      setHistory(res.results);
    } catch (err) {
      if (!handleSessionError(err)) setError(errorMessage(err));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    api<AdminProfile>(`/admin/profiles/${id}/`, { auth: "admin" })
      .then((p) => {
        setProfile(p);
        return loadHistory(); // after the view itself is logged, so "viewed" shows up in the history
      })
      .catch((err) => {
        if (handleSessionError(err)) return;
        setError(err instanceof ApiError && err.status === 404 ? "That profile does not exist." : errorMessage(err));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function changeStatus() {
    if (!confirming) return;
    setBusy(true);
    try {
      setProfile(await api<AdminProfile>(`/admin/profiles/${id}/${confirming}/`, { method: "POST", auth: "admin" }));
      setConfirming(null);
      await loadHistory();
    } catch (err) {
      if (!handleSessionError(err)) {
        setConfirming(null);
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const off = profile?.status === "deactivated";
  const d = profile?.demographics;
  const w = profile?.wellness;

  return (
    <Shell staff nav={adminNav("profiles")} box={<AdminBox email={admin?.email} />} onSignOut={signOut}>
      <header className="page-head">
        <div>
          <Link href="/admin" className="btn btn-sm" style={{ marginBottom: 14, textDecoration: "none", color: "inherit" }}>
            <IconArrowLeft size={14} /> Back to profiles
          </Link>
          <h1>{profile ? profile.display_name : "Member profile"}</h1>
          {profile && <p>{profile.email}</p>}
        </div>
        <ThemeToggle label />
      </header>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {!profile && !error && <div className="skeleton" style={{ height: 200 }} />}

      {profile && (
        <div className="content-grid">
          <div className="stack">
            <section className="card">
              <div className="detail-head">
                <Initials name={profile.display_name} large />
                <div>
                  <h2>Demographics</h2>
                  <small className="muted">Date of birth is hidden from admins</small>
                </div>
                <span className={`badge${off ? " off" : ""}`} style={{ marginLeft: "auto" }}>
                  {off ? "Deactivated" : "Active"}
                </span>
              </div>
              {d ? (
                <dl className="kv" style={{ gridTemplateColumns: "160px 1fr" }}>
                  <dt>Full name</dt>
                  <dd>{d.full_name}</dd>
                  <dt>Preferred name</dt>
                  <dd>{d.preferred_name || "—"}</dd>
                  <dt>Age range</dt>
                  <dd>{ageLabel(d.age_range)}</dd>
                  <dt>Gender</dt>
                  <dd>{labelOf(GENDERS, d.gender)}</dd>
                  <dt>City</dt>
                  <dd>{d.city || "—"}</dd>
                </dl>
              ) : (
                <p className="muted">Not filled in yet.</p>
              )}
            </section>

            <section className="card">
              <h2>Emergency contacts</h2>
              {profile.emergency_contacts.length === 0 ? (
                <p className="muted" style={{ marginTop: 8 }}>None added yet.</p>
              ) : (
                <div className="contact-list" style={{ marginTop: 12 }}>
                  {profile.emergency_contacts.map((c) => (
                    <div key={c.id} className="contact-card">
                      <div>
                        <strong>
                          {c.name} {c.is_primary && <span className="badge">Primary</span>}
                        </strong>
                        <small>
                          {labelOf(RELATIONSHIPS, c.relationship)} · {c.phone_masked}
                        </small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <p className="hint">Phone numbers are masked for admins.</p>
            </section>

            <section className="card">
              <h2>Wellness preferences</h2>
              {w ? (
                <>
                  <dl className="kv" style={{ gridTemplateColumns: "160px 1fr", marginTop: 12 }}>
                    <dt>Contact by</dt>
                    <dd>{labelOf(CONTACT_PREFERENCES, w.contact_preference)}</dd>
                    <dt>Activity level</dt>
                    <dd>{labelOf(ACTIVITY_LEVELS, w.activity_level)}</dd>
                    <dt>Diet</dt>
                    <dd>{labelOf(DIETS, w.diet_preference)}</dd>
                    <dt>Sleep goal</dt>
                    <dd>{w.sleep_goal_hours ? `${w.sleep_goal_hours} hours` : "—"}</dd>
                    <dt>Allergies</dt>
                    <dd>{w.has_allergies ? "Recorded (private)" : "None recorded"}</dd>
                  </dl>
                  <span className="hint">Goals</span>
                  <div className="chips">
                    {w.goals.length === 0 && <span className="muted">None selected</span>}
                    {w.goals.map((g) => (
                      <span key={g} className="chip-static">
                        {goalLabel(g)}
                      </span>
                    ))}
                  </div>
                </>
              ) : (
                <p className="muted" style={{ marginTop: 8 }}>Not filled in yet.</p>
              )}
              <p className="hint">Allergy text and lifestyle notes are private and never shown to admins.</p>
            </section>
          </div>

          <aside className="aside">
            <section className="card">
              <h2 style={{ fontSize: 15 }}>Record</h2>
              <dl className="kv" style={{ marginTop: 10 }}>
                <dt>Status</dt>
                <dd>
                  <CompletionBadge status={profile.completion_status} />
                </dd>
                <dt>Progress</dt>
                <dd>
                  <CompletionBar percent={profile.completion_percent} />
                </dd>
                <dt>Created</dt>
                <dd>{dateShort(profile.created_at)}</dd>
                <dt>Updated</dt>
                <dd>{dateTime(profile.updated_at)}</dd>
              </dl>
              <div className="detail-actions">
                {off ? (
                  <button className="btn" onClick={() => setConfirming("reactivate")}>
                    Reactivate profile
                  </button>
                ) : (
                  <button className="btn btn-danger" onClick={() => setConfirming("deactivate")}>
                    Deactivate profile
                  </button>
                )}
              </div>
            </section>

            <section className="card" aria-labelledby="history-title">
              <h2 id="history-title" style={{ fontSize: 15 }}>
                Profile history
              </h2>
              {history.length === 0 ? (
                <p className="muted" style={{ marginTop: 8 }}>No recorded events.</p>
              ) : (
                <ul className="timeline" style={{ marginTop: 12 }}>
                  {history.map((e) => (
                    <li key={e.id}>
                      <strong>{actionLabel(e.action)}</strong>
                      <small>
                        {dateTime(e.created_at)} · {e.actor_role}
                        {e.outcome !== "success" ? ` · ${e.outcome}` : ""}
                      </small>
                      {e.changed_fields.length > 0 && (
                        <div className="event-fields" style={{ marginTop: 4 }}>
                          {e.changed_fields.map((f) => (
                            <span key={f} className="chip-static muted-chip">
                              {f}
                            </span>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      )}

      {confirming && profile && (
        <ConfirmDialog
          title={confirming === "deactivate" ? "Deactivate this profile?" : "Reactivate this profile?"}
          confirmLabel={confirming === "deactivate" ? "Deactivate" : "Reactivate"}
          danger={confirming === "deactivate"}
          busy={busy}
          onConfirm={changeStatus}
          onCancel={() => setConfirming(null)}
        >
          {confirming === "deactivate"
            ? `${profile.display_name} will no longer be able to change their profile. The data is kept.`
            : `${profile.display_name} will be able to edit their profile again.`}
        </ConfirmDialog>
      )}
    </Shell>
  );
}
