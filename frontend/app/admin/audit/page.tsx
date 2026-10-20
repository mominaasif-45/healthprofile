"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminBox, adminNav } from "@/components/AdminChrome";
import { Shell } from "@/components/Shell";
import { ThemeToggle } from "@/components/Theme";
import { api, errorMessage, type AdminAuditEvent, type Page } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { ACTION_LABELS, actionLabel } from "@/lib/labels";
import { useAdmin } from "@/lib/useAdmin";

const PAGE_SIZE = 10;

export default function AdminAuditPage() {
  const { admin, signOut, handleSessionError } = useAdmin();
  const [action, setAction] = useState("");
  const [outcome, setOutcome] = useState("");
  const [actor, setActor] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<AdminAuditEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const actorError = actor && !/^[1-9]\d*$/.test(actor) ? "Actor must be a user id (a positive number)." : null;
  const dateError = after && before && after > before ? "“From” must be on or before “To”." : null;
  const invalid = actorError ?? dateError;

  const load = useCallback(async () => {
    if (invalid) return;
    setLoading(true);
    const qs = new URLSearchParams({ page: String(page) });
    if (action) qs.set("action", action);
    if (outcome) qs.set("outcome", outcome);
    if (actor) qs.set("actor", actor);
    if (after) qs.set("created_after", after);
    if (before) qs.set("created_before", before);
    try {
      setData(await api<Page<AdminAuditEvent>>(`/admin/audit-events/?${qs}`, { auth: "admin" }));
      setError(null);
    } catch (err) {
      if (!handleSessionError(err)) setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, action, outcome, actor, after, before, invalid]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const rows = data?.results ?? [];
  const total = data?.count ?? 0;
  const reset = () => {
    setAction("");
    setOutcome("");
    setActor("");
    setAfter("");
    setBefore("");
    setPage(1);
  };
  const change = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setter(e.target.value);
    setPage(1);
  };

  return (
    <Shell staff nav={adminNav("audit")} box={<AdminBox email={admin?.email} />} onSignOut={signOut}>
      <header className="page-head">
        <div>
          <h1>Audit log</h1>
          <p>Read-only record of profile edits and admin actions. It stores who, what and when, never values.</p>
        </div>
        <ThemeToggle label />
      </header>

      <div className="filters" role="group" aria-label="Audit filters">
        <div className="field">
          <label className="label" htmlFor="a-action">
            Action
          </label>
          <select id="a-action" className="select" value={action} onChange={change(setAction)}>
            <option value="">Any</option>
            {Object.entries(ACTION_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="a-outcome">
            Outcome
          </label>
          <select id="a-outcome" className="select" value={outcome} onChange={change(setOutcome)}>
            <option value="">Any</option>
            <option value="success">Success</option>
            <option value="denied">Denied</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div className="field">
          <label className="label" htmlFor="a-actor">
            Actor (user id)
          </label>
          <input id="a-actor" className="input" inputMode="numeric" placeholder="e.g. 12" value={actor} onChange={change(setActor)} aria-invalid={!!actorError} />
        </div>
        <div className="field">
          <label className="label" htmlFor="a-after">
            From
          </label>
          <input id="a-after" type="date" className="input" value={after} onChange={change(setAfter)} />
        </div>
        <div className="field">
          <label className="label" htmlFor="a-before">
            To
          </label>
          <input id="a-before" type="date" className="input" value={before} onChange={change(setBefore)} />
        </div>
        <button className="btn btn-sm" onClick={reset} disabled={!(action || outcome || actor || after || before)}>
          Clear filters
        </button>
      </div>

      {(invalid || error) && (
        <div className="form-error" role="alert">
          {invalid ?? error}
        </div>
      )}

      <section className="table-card" aria-busy={loading}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Actor</th>
                <th className="col-hide-sm">Target</th>
                <th>Fields</th>
                <th>Outcome</th>
                <th className="col-hide-sm">Request</th>
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
                    {e.actor_role}
                    {e.actor ? ` #${e.actor}` : ""}
                  </td>
                  <td className="col-hide-sm">{e.target_type ? `${e.target_type.replace("_", " ")} #${e.target_id}` : "—"}</td>
                  <td>
                    <div className="event-fields">
                      {e.changed_fields.length === 0 && <span className="muted">—</span>}
                      {e.changed_fields.map((f) => (
                        <span key={f} className="chip-static muted-chip">
                          {f}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <span className={`badge${e.outcome === "success" ? "" : " off"}`}>{e.outcome}</span>
                  </td>
                  <td className="mono col-hide-sm" title={e.request_id ?? ""}>
                    {e.request_id ? e.request_id.slice(0, 8) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!loading && rows.length === 0 && !error && <div className="empty">No events match your filters.</div>}
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
              ? "Showing 0 events"
              : `Showing ${(page - 1) * PAGE_SIZE + 1}–${(page - 1) * PAGE_SIZE + rows.length} of ${total} events`}
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
    </Shell>
  );
}
