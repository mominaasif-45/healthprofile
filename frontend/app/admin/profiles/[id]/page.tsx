"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { IconArrowLeft, IconUsers } from "@/components/Icons";
import { Initials, Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ApiError, api, errorMessage, type AdminProfile } from "@/lib/api";
import { ageLabel, contactLabel, dateShort, dateTime } from "@/lib/format";
import { useAdmin } from "@/lib/useAdmin";

export default function AdminProfileDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { admin, signOut, handleSessionError } = useAdmin();
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<AdminProfile>(`/admin/profiles/${id}/`, { auth: "admin" })
      .then(setProfile)
      .catch((err) => {
        if (handleSessionError(err)) return;
        setError(err instanceof ApiError && err.status === 404 ? "That profile does not exist." : errorMessage(err));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function deactivate() {
    setBusy(true);
    try {
      setProfile(await api<AdminProfile>(`/admin/profiles/${id}/deactivate/`, { method: "POST", auth: "admin" }));
      setConfirming(false);
    } catch (err) {
      if (!handleSessionError(err)) {
        setConfirming(false);
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  const off = profile?.status === "deactivated";

  return (
    <Shell
      staff
      nav={[{ href: "/admin", label: "Member profiles", icon: <IconUsers />, current: true }]}
      box={
        <>
          <strong>
            <span className="dot" />
            Session active
          </strong>
          Signed in as {admin?.email ?? "…"}. Ends after 30 min idle.
        </>
      }
      onSignOut={signOut}
    >
      <header className="page-head">
        <div>
          <Link href="/admin" className="btn btn-sm" style={{ marginBottom: 14, textDecoration: "none", color: "inherit" }}>
            <IconArrowLeft size={14} /> Back to profiles
          </Link>
          <h1>{profile ? profile.full_name : "Member profile"}</h1>
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
                <Initials name={profile.full_name} large />
                <div>
                  <h2>Personal details</h2>
                  <small className="muted">Member since {dateShort(profile.member_since)}</small>
                </div>
                <span className={`badge${off ? " off" : ""}`} style={{ marginLeft: "auto" }}>
                  {off ? "Deactivated" : "Active"}
                </span>
              </div>
              <dl className="kv" style={{ gridTemplateColumns: "160px 1fr" }}>
                <dt>Full name</dt>
                <dd>{profile.full_name}</dd>
                <dt>Account name</dt>
                <dd>{profile.account_name}</dd>
                <dt>Age range</dt>
                <dd>{ageLabel(profile.age_range)}</dd>
                <dt>Date of birth</dt>
                <dd>{profile.date_of_birth ? dateShort(profile.date_of_birth) : "Not provided"}</dd>
                <dt>Contact preference</dt>
                <dd>{contactLabel(profile.contact_preference)}</dd>
              </dl>
            </section>

            <section className="card">
              <h2>Wellness goals</h2>
              <div className="chips">
                {profile.wellness_goals.length === 0 && <span className="muted">None selected</span>}
                {profile.wellness_goals.map((g) => (
                  <span key={g} className="chip-static">
                    {g}
                  </span>
                ))}
              </div>
              <span className="hint">Lifestyle notes</span>
              <p style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{profile.lifestyle_notes || "None provided."}</p>
            </section>

            <section className="card">
              <h2>Allergies and emergency contact</h2>
              <dl className="kv" style={{ gridTemplateColumns: "160px 1fr", marginTop: 12 }}>
                <dt>Allergies</dt>
                <dd>{profile.allergies || "None listed"}</dd>
                <dt>Emergency contact</dt>
                <dd>{profile.emergency_contact_name || "—"}</dd>
                <dt>Contact phone</dt>
                <dd>{profile.emergency_contact_phone || "—"}</dd>
              </dl>
            </section>
          </div>

          <aside className="aside">
            <section className="card">
              <h2 style={{ fontSize: 15 }}>Record</h2>
              <dl className="kv" style={{ marginTop: 10 }}>
                <dt>Strength</dt>
                <dd>{profile.completeness.percent}%</dd>
                <dt>Created</dt>
                <dd>{dateTime(profile.created_at)}</dd>
                <dt>Updated</dt>
                <dd>{dateTime(profile.updated_at)}</dd>
              </dl>
              <div className="detail-actions">
                <button className="btn btn-danger" disabled={off} onClick={() => setConfirming(true)}>
                  {off ? "Already deactivated" : "Deactivate profile"}
                </button>
              </div>
            </section>
          </aside>
        </div>
      )}

      {confirming && profile && (
        <div className="modal-back" role="presentation" onClick={() => !busy && setConfirming(false)}>
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="dlg-title" onClick={(e) => e.stopPropagation()}>
            <h2 id="dlg-title">Deactivate this profile?</h2>
            <p className="muted">
              {profile.full_name} will no longer be able to edit their profile. The data is kept.
            </p>
            <div className="actions">
              <button className="btn" onClick={() => setConfirming(false)} disabled={busy}>
                Cancel
              </button>
              <button className="btn btn-danger" onClick={deactivate} disabled={busy} autoFocus>
                {busy ? "Deactivating…" : "Deactivate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
