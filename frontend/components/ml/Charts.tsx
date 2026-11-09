import type { ReactNode } from "react";

/** The disclaimer box every tab starts with (role="note" so screen readers announce it as an aside). */
export function Disclaimer({ children }: { children: ReactNode }) {
  return (
    <div className="info-box" role="note" style={{ marginBottom: 16 }}>
      {/* .info-box is a flex row: one wrapper keeps the sentence together instead of splitting it into columns. */}
      <div>{children}</div>
    </div>
  );
}

export const f3 = (n: number) => n.toFixed(3);
export const pct = (n: number) => `${Math.round(n * 100)}%`;
export const signed = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(3)}`;

/**
 * Horizontal bars drawn with plain SVG. Every bar carries its label and value as text, so nothing depends on colour.
 * Values below zero are drawn as zero-length bars (their text still shows the real value).
 */
export function BarChart({ title, rows, max }: { title: string; rows: { label: string; value: number; text: string }[]; max?: number }) {
  const top = max ?? Math.max(...rows.map((r) => r.value), 0.0001);
  const rowH = 26;
  const labelW = 170;
  const barW = 260;
  const height = rows.length * rowH + 8;
  return (
    <svg role="img" aria-label={title} viewBox={`0 0 ${labelW + barW + 90} ${height}`} width="100%"
         style={{ maxWidth: 560, display: "block" }}>
      <title>{title}</title>
      {rows.map((r, i) => {
        const y = i * rowH + 4;
        const w = Math.max(0, (r.value / top) * barW);
        return (
          <g key={r.label}>
            <text x={labelW - 8} y={y + 15} textAnchor="end" fontSize="12" fill="currentColor">{r.label}</text>
            <rect x={labelW} y={y + 3} width={w} height={rowH - 10} rx="3" fill="var(--primary, #2f7d6d)" />
            <text x={labelW + w + 6} y={y + 15} fontSize="12" fill="currentColor">{r.text}</text>
          </g>
        );
      })}
    </svg>
  );
}

/**
 * The 2D PCA scatter. Cluster 1 is drawn as circles and cluster 2 as squares (and in two colours), so the clusters can
 * be told apart without colour. Each point has data-point so tests can count them.
 */
export function Scatter({ title, points }: { title: string; points: [number, number, number][] }) {
  const size = 360;
  const pad = 24;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) => pad + ((x - minX) / (maxX - minX || 1)) * (size - 2 * pad);
  const sy = (y: number) => size - pad - ((y - minY) / (maxY - minY || 1)) * (size - 2 * pad);
  return (
    <svg role="img" aria-label={title} viewBox={`0 0 ${size} ${size + 30}`} width="100%"
         style={{ maxWidth: 420, display: "block" }}>
      <title>{title}</title>
      <rect x={pad} y={pad} width={size - 2 * pad} height={size - 2 * pad} fill="none" stroke="currentColor" strokeOpacity="0.25" />
      <text x={size / 2} y={size - 4} textAnchor="middle" fontSize="11" fill="currentColor">PCA direction 1</text>
      <text x={10} y={size / 2} fontSize="11" fill="currentColor" transform={`rotate(-90 10 ${size / 2})`} textAnchor="middle">
        PCA direction 2
      </text>
      {points.map(([x, y, c], i) =>
        c === 1 ? (
          <circle key={i} data-point="" cx={sx(x)} cy={sy(y)} r="2.6" fill="#2f7d6d" fillOpacity="0.6" />
        ) : (
          <rect key={i} data-point="" x={sx(x) - 2.4} y={sy(y) - 2.4} width="4.8" height="4.8" fill="#b4542f" fillOpacity="0.6" />
        )
      )}
      <g transform={`translate(${pad}, ${size + 14})`} fontSize="12" fill="currentColor">
        <circle cx="6" cy="0" r="4" fill="#2f7d6d" />
        <text x="16" y="4">Cluster 1 (circles)</text>
        <rect x="150" y="-4" width="8" height="8" fill="#b4542f" />
        <text x="164" y="4">Cluster 2 (squares)</text>
      </g>
    </svg>
  );
}
