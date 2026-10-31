import { COMPLETION_LABELS } from "@/lib/labels";

/** A small progress bar with the percentage. Used in tables (compact) and cards. */
export function CompletionBar({ percent, status }: { percent: number; status?: string }) {
  return (
    <div className="completion" title={status ? COMPLETION_LABELS[status] : undefined}>
      <div
        className="completion-track"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Profile completion ${percent}%`}
      >
        <i style={{ width: `${percent}%` }} />
      </div>
      <span>{percent}%</span>
    </div>
  );
}

export function CompletionBadge({ status }: { status: string }) {
  const cls = status === "complete" ? "" : status === "in_progress" ? " warn" : " off";
  return <span className={`badge${cls}`}>{COMPLETION_LABELS[status] ?? status}</span>;
}
