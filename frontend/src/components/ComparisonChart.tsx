import { asNumber, formatPct } from "../lib/format";

type Row = {
  label: string;
  current: number | string;
  target: number | string;
};

export function ComparisonChart({ rows }: { rows: Row[] }) {
  const items = rows.map((row) => ({
    label: row.label,
    current: asNumber(row.current) * 100,
    target: asNumber(row.target) * 100,
  }));
  const max = Math.max(1, ...items.flatMap((row) => [row.current, row.target]));

  return (
    <div className="compare">
      {items.map((row) => (
        <div key={row.label} className="compare-row">
          <div className="compare-label">{row.label}</div>
          <div className="compare-bars">
            <div
              className="compare-bar current"
              style={{ width: `${(row.current / max) * 100}%` }}
              title={`Current ${row.current.toFixed(1)}%`}
            />
            <div
              className="compare-bar target"
              style={{ width: `${(row.target / max) * 100}%` }}
              title={`Target ${row.target.toFixed(1)}%`}
            />
          </div>
          <div className="compare-meta">
            {formatPct(row.current / 100)} → {formatPct(row.target / 100)}
          </div>
        </div>
      ))}
      <div className="compare-legend">
        <span><i className="swatch current" /> Current</span>
        <span><i className="swatch target" /> Target</span>
      </div>
    </div>
  );
}
