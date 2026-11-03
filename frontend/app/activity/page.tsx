"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { IconClock, IconShield, IconTarget, IconUser, IconUsers } from "@/components/Icons";
import { Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { ApiError, api, errorMessage, userLogout, type AuditEvent, type Page } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { actionLabel } from "@/lib/labels";

export default function ActivityPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AuditEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<Page<AuditEvent>>(`/profiles/me/activity/?page=${page}`));
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) router.replace("/login");
      else setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, router]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  async function signOut() {
    await userLogout().catch(() => {});
    router.replace("/login");
  }

  const rows = data?.results ?? [];

  return (
    <Shell
      nav={[
        { href: "/profile", label: "My profile", icon: <IconUser /> },
        { href: "/profile#contacts", label: "Emergency contacts", icon: <IconUsers /> },
        { href: "/profile#wellness", label: "Wellness goals", icon: <IconTarget /> },
        { href: "/activity", label: "My activity", icon: <IconClock />, current: true },
        { href: "/profile#privacy", label: "Privacy and security", icon: <IconShield /> },
      ]}
      box={
        <>
          <strong>Privacy</strong>
          This list shows which fields changed and when, never the values you entered.
        </>
      }
      onSignOut={signOut}
    >
      <header className="page-head">
        <div>
          <span className="eyebrow">Activity</span>
          <h1>My activity</h1>
          <p>Every change to your profile, newest first. Only field names are recorded, never what you typed.</p>
        </div>
        <ThemeToggle />
      </header>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <section className="table-card" aria-busy={loading}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>What happened</th>
                <th>Fields changed</th>
                <th>Result</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} style={{ cursor: "default" }}>
                  <td>{dateTime(e.created_at)}</td>
                  <td>
                    <strong>{actionLabel(e.action)}</strong>
                  </td>
                  <td>
                    <div className="event-fields">
                      {e.changed_fields.length === 0 && <span className="muted">—</span>}
                      {e.changed_fields.map((f) => (
                        <span key={f} className="chip-static">
                          {f}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className={`badge${e.outcome === "success" ? "" : " off"}`}>{e.outcome}</span>
                  </td>
                  <td className="mono" title={e.request_id ?? ""}>
                    {e.request_id ? e.request_id.slice(0, 8) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && rows.length === 0 && !error && <div className="empty">No activity yet. Changes you make to your profile will appear here.</div>}
          {loading && rows.length === 0 && (
            <div style={{ padding: 16, display: "grid", gap: 14 }}>
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton" />
              ))}
            </div>
          )}
        </div>
        <div className="table-foot">
          <span>{data ? `${data.count} ${data.count === 1 ? "event" : "events"}` : ""}</span>
          <div className="actions">
            <button className="btn btn-sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <button className="btn btn-sm" disabled={!data?.next || loading} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </div>
      </section>
    </Shell>
  );
}
