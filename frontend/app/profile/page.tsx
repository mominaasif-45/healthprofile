"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { CompletionBadge } from "@/components/Completion";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { IconCheck, IconClock, IconLock, IconShield, IconTarget, IconUser, IconUsers } from "@/components/Icons";
import { ContactsCard } from "@/components/profile/ContactsCard";
import { DemographicsCard } from "@/components/profile/DemographicsCard";
import { WellnessCard } from "@/components/profile/WellnessCard";
import { Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ApiError, api, errorMessage, minutesUntilRenewal, userLogout, type Profile, type User } from "@/lib/api";
import { dateTime, greeting } from "@/lib/format";

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [renews, setRenews] = useState<number | null>(null);
  // The "Create your wellness profile" heading: where focus goes after the profile is deleted,
  // because the Delete button and its whole section disappear with the profile.
  const createHeading = useRef<HTMLHeadingElement>(null);
  // Bumped after a delete; the effect below moves focus once the create card has rendered.
  const [refocus, setRefocus] = useState(0);

  useEffect(() => {
    if (refocus > 0) createHeading.current?.focus();
  }, [refocus]);

  const reload = useCallback(async () => {
    try {
      setProfile(await api<Profile>("/profiles/me/"));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setProfile(null);
      else throw err;
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setUser(await api<User>("/auth/me/"));
        await reload();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) router.replace("/login");
        else setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [reload, router]);

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

  async function afterChange(message: string) {
    setError(null);
    try {
      await reload();
      setToast(message);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function createProfile() {
    setCreating(true);
    setError(null);
    try {
      await api("/profiles/me/", { method: "POST" });
      await afterChange("Profile created. Fill in each section below.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function deleteProfile() {
    setDeleting(true);
    try {
      await api("/profiles/me/", { method: "DELETE" });
      setConfirmDelete(false);
      setProfile(null);
      setToast("Profile deleted. Your account is still active.");
      setRefocus((n) => n + 1);
    } catch (err) {
      setConfirmDelete(false);
      setError(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  async function signOut() {
    await userLogout().catch(() => {});
    router.replace("/login");
  }

  if (loading) {
    return (
      <div className="main" style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="skeleton" style={{ width: 200, height: 28, marginBottom: 20 }} />
        <div className="skeleton" style={{ height: 220 }} />
      </div>
    );
  }

  const deactivated = profile?.status === "deactivated";
  const firstName = (user?.name ?? "").split(" ")[0];
  const steps = [
    { label: "Demographics", done: !!profile?.demographics },
    { label: "Emergency contact", done: (profile?.emergency_contacts.length ?? 0) > 0 },
    { label: "Wellness preferences", done: !!profile?.wellness },
    { label: "At least one goal", done: (profile?.wellness?.goals.length ?? 0) > 0 },
  ];

  return (
    <Shell
      nav={[
        { href: "#profile", label: "My profile", icon: <IconUser />, current: true },
        { href: "#contacts", label: "Emergency contacts", icon: <IconUsers /> },
        { href: "#wellness", label: "Wellness goals", icon: <IconTarget /> },
        { href: "/activity", label: "My activity", icon: <IconClock /> },
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
          <p>Each section saves on its own. Only you and clinic admins can see your profile.</p>
        </div>
        <ThemeToggle />
      </header>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}
      {deactivated && (
        <div className="form-error" role="status">
          This profile has been deactivated by an administrator. You can read it but not change or delete it.
        </div>
      )}

      {!profile ? (
        <section className="card" style={{ maxWidth: 560 }}>
          <h2 ref={createHeading} tabIndex={-1}>
            Create your wellness profile
          </h2>
          <p className="sub">
            It has four short sections: demographics, an emergency contact, wellness preferences and goals. You can fill
            them in any order.
          </p>
          <button className="btn btn-primary" onClick={createProfile} disabled={creating}>
            {creating ? "Creating…" : "Create my profile"}
          </button>
        </section>
      ) : (
        <div className="content-grid">
          <div className="stack">
            <DemographicsCard
              key={`d-${profile.id}-${profile.demographics?.created_at ?? "new"}`}
              section={profile.demographics}
              fallbackName={user?.name ?? ""}
              readOnly={deactivated}
              onSaved={afterChange}
            />
            <ContactsCard contacts={profile.emergency_contacts} readOnly={deactivated} onChanged={afterChange} />
            <WellnessCard
              key={`w-${profile.id}-${profile.wellness?.created_at ?? "new"}`}
              section={profile.wellness}
              readOnly={deactivated}
              onSaved={afterChange}
            />

            {!deactivated && (
              <section className="card danger-zone" aria-labelledby="danger-title">
                <h2 id="danger-title">Delete my profile</h2>
                <p className="sub">
                  Removes your profile and every section. Your account stays, so you can create a new profile later.
                </p>
                <button className="btn btn-danger" onClick={() => setConfirmDelete(true)}>
                  Delete my profile
                </button>
              </section>
            )}
          </div>

          <aside className="aside">
            <section className="hero-card" aria-label="Profile completion">
              <div className="row">
                <strong>Profile completion</strong>
                <span className="badge">{deactivated ? "Deactivated" : "Active"}</span>
              </div>
              <div className="big">{profile.completion.percent}%</div>
              <div className="bar" role="progressbar" aria-valuenow={profile.completion.percent} aria-valuemin={0} aria-valuemax={100}>
                <i style={{ width: `${profile.completion.percent}%` }} />
              </div>
              <ul className="steps">
                {steps.map((s) => (
                  <li key={s.label} className={s.done ? "done" : ""}>
                    <span className="tick">{s.done && <IconCheck size={12} />}</span>
                    {s.label}
                  </li>
                ))}
              </ul>
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
                  <small>Last updated {dateTime(profile.updated_at)}</small>
                </div>
              </div>
              <div style={{ marginTop: 6 }}>
                <CompletionBadge status={profile.completion.status} />
              </div>
            </section>
          </aside>
        </div>
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete your profile?"
          confirmLabel="Delete my profile"
          typeToConfirm="DELETE"
          busy={deleting}
          onConfirm={deleteProfile}
          onCancel={() => setConfirmDelete(false)}
          returnFocusFallback={createHeading}
        >
          This permanently removes your demographics, emergency contacts, wellness preferences and goals. Your account
          stays active.
        </ConfirmDialog>
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </Shell>
  );
}
