"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { IconSearch, IconUsers } from "@/components/Icons";
import { Initials, Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { api, errorMessage, type AdminProfile, type AdminRow, type Page } from "@/lib/api";
import { ageLabel, contactLabel, dateShort, dateTime } from "@/lib/format";
import { useAdmin } from "@/lib/useAdmin";

const PAGE_SIZE = 10;
type StatusFilter = "" | "active" | "deactivated";

export default function AdminPage() {
  const { admin, signOut, handleSessionError } = useAdmin();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AdminRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const seq = useRef(0);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  // Always rendered, so focus has somewhere to go when the detail panel disappears.
  const pageHeading = useRef<HTMLHeadingElement>(null);
  // Bumped after a deactivate refresh; the effect below moves focus once the new list has rendered.
  const [refocus, setRefocus] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    const qs = new URLSearchParams({ page: String(page) });
    if (debounced) qs.set("search", debounced);
    if (status) qs.set("status", status);
    try {
      const res = await api<Page<AdminRow>>(`/admin/profiles/?${qs}`, { auth: "admin" });
      if (mine !== seq.current) return; // a newer request already won
      setData(res);
      setError(null);
      setSelectedId((cur) => (cur && res.results.some((r) => r.id === cur) ? cur : (res.results[0]?.id ?? null)));
    } catch (err) {
      if (mine !== seq.current || handleSessionError(err)) return;
      setError(errorMessage(err));
    } finally {
      if (mine === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debounced, status]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  // Runs after the refreshed selection is committed: the detail heading exists only if a profile is
  // still selected (e.g. not when the Active filter just lost its last match), otherwise use the page heading.
  useEffect(() => {
    if (refocus === 0) return;
    (detailHeading.current ?? pageHeading.current)?.focus();
  }, [refocus]);

  const rows = data?.results ?? [];
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const total = data?.count ?? 0;
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = (page - 1) * PAGE_SIZE + rows.length;

  async function deactivate() {
    if (!selected) return;
    setBusy(true);
    try {
      await api<AdminProfile>(`/admin/profiles/${selected.id}/deactivate/`, { method: "POST", auth: "admin" });
      setConfirming(false);
      setToast(`${selected.full_name} was deactivated`);
      await load();
      setRefocus((n) => n + 1); // the Deactivate button is now disabled or gone, so it cannot take focus back
    } catch (err) {
      if (!handleSessionError(err)) {
        setConfirming(false);
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

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
          <h1 ref={pageHeading} tabIndex={-1}>
            Member profiles
          </h1>
          <p>Search and review synthetic member profiles. Admin-only view.</p>
        </div>
        <ThemeToggle label />
      </header>

      <div className="toolbar">
        <div className="search">
          <IconSearch size={16} />
          <input
            className="input"
            type="search"
            placeholder="Search by name or email"
            aria-label="Search by name or email"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="tabs" role="group" aria-label="Filter by status">
          {(
            [
              ["", "All"],
              ["active", "Active"],
              ["deactivated", "Deactivated"],
            ] as [StatusFilter, string][]
          ).map(([value, label]) => (
            <button
              key={label}
              type="button"
              className="tab"
              aria-pressed={status === value}
              onClick={() => {
                setStatus(value);
                setPage(1);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="form-error" role="alert">
          {error}
        </div>
      )}

      <div className="admin-grid">
        <section className="table-card" aria-busy={loading}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Age range</th>
                  <th>Contact</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    aria-selected={r.id === selectedId}
                    tabIndex={0}
                    onClick={() => setSelectedId(r.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedId(r.id);
                      }
                    }}
                  >
                    <td>
                      <div className="who">
                        <Initials name={r.full_name} />
                        <div>
                          <strong>{r.full_name}</strong>
                          <small>{r.email}</small>
                        </div>
                      </div>
                    </td>
                    <td>{ageLabel(r.age_range)}</td>
                    <td>{contactLabel(r.contact_preference)}</td>
                    <td>
                      <span className={`badge${r.status === "deactivated" ? " off" : ""}`}>
                        {r.status === "active" ? "Active" : "Deactivated"}
                      </span>
                    </td>
                    <td>{dateShort(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && rows.length === 0 && !error && (
              <div className="empty">No profiles match your search.</div>
            )}
            {loading && rows.length === 0 && (
              <div style={{ padding: 16, display: "grid", gap: 14 }}>
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="skeleton" />
                ))}
              </div>
            )}
          </div>
          <div className="table-foot">
            <span>
              {total === 0
                ? "Showing 0 profiles"
                : total <= PAGE_SIZE && page === 1
                  ? `Showing ${total} of ${total} ${total === 1 ? "profile" : "profiles"}`
                  : `Showing ${from}–${to} of ${total} profiles`}
            </span>
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

        {selected && (
          <aside className="card" aria-label="Selected profile">
            <div className="detail-head">
              <Initials name={selected.full_name} large />
              <div style={{ minWidth: 0 }}>
                <h2 ref={detailHeading} tabIndex={-1}>
                  {selected.full_name}
                </h2>
                <small className="muted" style={{ overflowWrap: "anywhere" }}>
                  {selected.email}
                </small>
              </div>
              <span className={`badge${selected.status === "deactivated" ? " off" : ""}`} style={{ marginLeft: "auto" }}>
                {selected.status === "active" ? "Active" : "Deactivated"}
              </span>
            </div>
            <dl className="kv">
              <dt>Age range</dt>
              <dd>{ageLabel(selected.age_range)}</dd>
              <dt>Contact by</dt>
              <dd>{contactLabel(selected.contact_preference)}</dd>
              <dt>Allergies</dt>
              <dd>{selected.allergies || "None listed"}</dd>
              <dt>Emergency</dt>
              <dd>{selected.emergency_contact_name || "—"}</dd>
              <dt>Last updated</dt>
              <dd>{dateTime(selected.updated_at)}</dd>
            </dl>
            <span className="hint">Wellness goals</span>
            <div className="chips">
              {selected.wellness_goals.length === 0 && <span className="muted">None selected</span>}
              {selected.wellness_goals.map((g) => (
                <span key={g} className="chip-static">
                  {g}
                </span>
              ))}
            </div>
            <div className="detail-actions">
              <Link href={`/admin/profiles/${selected.id}`} className="btn btn-primary" style={{ color: "var(--on-primary)" }}>
                View full profile
              </Link>
              <button
                className="btn btn-danger"
                disabled={selected.status === "deactivated"}
                onClick={() => setConfirming(true)}
              >
                {selected.status === "deactivated" ? "Already deactivated" : "Deactivate profile"}
              </button>
            </div>
          </aside>
        )}
      </div>

      {confirming && selected && (
        <ConfirmDialog
          title="Deactivate this profile?"
          confirmLabel="Deactivate"
          busyLabel="Deactivating…"
          busy={busy}
          onConfirm={deactivate}
          onCancel={() => setConfirming(false)}
          returnFocusFallback={pageHeading}
        >
          {selected.full_name} will no longer be able to edit their profile. This is recorded as a status change and
          the data is kept.
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
