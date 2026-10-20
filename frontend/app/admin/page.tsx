"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AdminBox, adminNav } from "@/components/AdminChrome";
import { CompletionBadge, CompletionBar } from "@/components/Completion";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { IconSearch } from "@/components/Icons";
import { Initials, Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { api, errorMessage, type AdminProfile, type AdminRow, type Page } from "@/lib/api";
import { dateShort } from "@/lib/format";
import { useAdmin } from "@/lib/useAdmin";

const PAGE_SIZE = 10;
type StatusFilter = "" | "active" | "deactivated";

const ORDERINGS = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "-completion_percent", label: "Most complete" },
  { value: "completion_percent", label: "Least complete" },
];

export default function AdminPage() {
  const { admin, signOut, handleSessionError } = useAdmin();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [completion, setCompletion] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AdminRow> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [confirming, setConfirming] = useState<"deactivate" | "reactivate" | null>(null);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const dateError = after && before && after > before ? "“From” must be on or before “To”." : null;

  const load = useCallback(async () => {
    if (dateError) return;
    const mine = ++seq.current;
    setLoading(true);
    const qs = new URLSearchParams({ page: String(page), ordering });
    if (debounced) qs.set("search", debounced);
    if (status) qs.set("status", status);
    if (completion) qs.set("completion_status", completion);
    if (after) qs.set("created_after", after);
    if (before) qs.set("created_before", before);
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
  }, [page, debounced, status, completion, ordering, after, before, dateError]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  const rows = data?.results ?? [];
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const total = data?.count ?? 0;
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = (page - 1) * PAGE_SIZE + rows.length;
  const filtersActive = !!(search || status || completion || after || before || ordering !== "-created_at");

  function clearFilters() {
    setSearch("");
    setDebounced("");
    setStatus("");
    setCompletion("");
    setOrdering("-created_at");
    setAfter("");
    setBefore("");
    setPage(1);
  }

  async function changeStatus() {
    if (!selected || !confirming) return;
    setBusy(true);
    try {
      await api<AdminProfile>(`/admin/profiles/${selected.id}/${confirming}/`, { method: "POST", auth: "admin" });
      setConfirming(null);
      setToast(`${selected.display_name} was ${confirming}d`);
      await load();
    } catch (err) {
      if (!handleSessionError(err)) {
        setConfirming(null);
        setError(errorMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell staff nav={adminNav("profiles")} box={<AdminBox email={admin?.email} />} onSignOut={signOut}>
      <header className="page-head">
        <div>
          <h1>Member profiles</h1>
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

      <div className="filters" role="group" aria-label="More filters">
        <div className="field">
          <label className="label" htmlFor="f-completion">
            Completion
          </label>
          <select id="f-completion" className="select" value={completion} onChange={(e) => { setCompletion(e.target.value); setPage(1); }}>
            <option value="">Any</option>
            <option value="not_started">Not started</option>
            <option value="in_progress">In progress</option>
            <option value="complete">Complete</option>
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="f-after">
            Created from
          </label>
          <input id="f-after" type="date" className="input" value={after} onChange={(e) => { setAfter(e.target.value); setPage(1); }} />
        </div>
        <div className="field">
          <label className="label" htmlFor="f-before">
            Created to
          </label>
          <input id="f-before" type="date" className="input" value={before} onChange={(e) => { setBefore(e.target.value); setPage(1); }} />
        </div>
        <div className="field">
          <label className="label" htmlFor="f-order">
            Sort by
          </label>
          <select id="f-order" className="select" value={ordering} onChange={(e) => { setOrdering(e.target.value); setPage(1); }}>
            {ORDERINGS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button className="btn btn-sm" onClick={clearFilters} disabled={!filtersActive}>
          Clear filters
        </button>
      </div>

      {(error || dateError) && (
        <div className="form-error" role="alert">
          {dateError ?? error}
        </div>
      )}

      <div className="admin-grid">
        <section className="table-card" aria-busy={loading}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Member</th>
                  <th>Completion</th>
                  <th>Status</th>
                  <th className="col-hide-sm">Created</th>
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
                        <Initials name={r.display_name} />
                        <div>
                          <strong>{r.display_name}</strong>
                          <small>{r.email}</small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <CompletionBar percent={r.completion_percent} status={r.completion_status} />
                    </td>
                    <td>
                      <span className={`badge${r.status === "deactivated" ? " off" : ""}`}>
                        {r.status === "active" ? "Active" : "Deactivated"}
                      </span>
                    </td>
                    <td className="col-hide-sm">{dateShort(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!loading && rows.length === 0 && !error && <div className="empty">No profiles match your filters.</div>}
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
              <Initials name={selected.display_name} large />
              <div style={{ minWidth: 0 }}>
                <h2>{selected.display_name}</h2>
                <small className="muted" style={{ overflowWrap: "anywhere" }}>
                  {selected.email}
                </small>
              </div>
              <span className={`badge${selected.status === "deactivated" ? " off" : ""}`} style={{ marginLeft: "auto" }}>
                {selected.status === "active" ? "Active" : "Deactivated"}
              </span>
            </div>
            <dl className="kv">
              <dt>Completion</dt>
              <dd>
                <CompletionBadge status={selected.completion_status} />
              </dd>
              <dt>Progress</dt>
              <dd>
                <CompletionBar percent={selected.completion_percent} />
              </dd>
              <dt>Created</dt>
              <dd>{dateShort(selected.created_at)}</dd>
            </dl>
            <p className="hint" style={{ marginBottom: 12 }}>
              Sensitive details (date of birth, allergies, notes, phone numbers) are never shown to admins.
            </p>
            <div className="detail-actions">
              <Link href={`/admin/profiles/${selected.id}`} className="btn btn-primary" style={{ color: "var(--on-primary)" }}>
                View full profile
              </Link>
              {selected.status === "active" ? (
                <button className="btn btn-danger" onClick={() => setConfirming("deactivate")}>
                  Deactivate profile
                </button>
              ) : (
                <button className="btn" onClick={() => setConfirming("reactivate")}>
                  Reactivate profile
                </button>
              )}
            </div>
          </aside>
        )}
      </div>

      {confirming && selected && (
        <ConfirmDialog
          title={confirming === "deactivate" ? "Deactivate this profile?" : "Reactivate this profile?"}
          confirmLabel={confirming === "deactivate" ? "Deactivate" : "Reactivate"}
          danger={confirming === "deactivate"}
          busy={busy}
          onConfirm={changeStatus}
          onCancel={() => setConfirming(null)}
        >
          {confirming === "deactivate"
            ? `${selected.display_name} will still be able to read their profile but not change or delete it. The data is kept and the action is recorded in the audit log.`
            : `${selected.display_name} will be able to edit their profile again. The action is recorded in the audit log.`}
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
