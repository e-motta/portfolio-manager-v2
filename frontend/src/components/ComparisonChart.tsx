import { useId } from "react";
import { asNumber, formatPctPoints } from "../lib/format";

type Row = {
  label: string;
  current: number | string;
  target: number | string;
  delta?: number | string;
};

export function ComparisonChart({ rows }: { rows: Row[] }) {
  const chartId = useId();
  const items = rows.map((row) => {
    const current = asNumber(row.current) * 100;
    const target = asNumber(row.target) * 100;
    const drift = current - target;
    return { label: row.label, current, target, drift };
  });

  const maxDrift = Math.max(1, ...items.map((row) => Math.abs(row.drift)));

  return (
    <div
      className="compare compare--drift"
      role="group"
      aria-label="Portfolio allocation drift from targets"
    >
      {items.map((row, index) => {
        const barWidth = Math.abs(row.drift) / maxDrift * 50;
        const isOver = row.drift > 0;
        const driftLabel = isOver ? "overweight" : row.drift < 0 ? "underweight" : "on target";
        const rowId = `${chartId}-row-${index}`;
        return (
          <div
            key={row.label}
            className="compare-row"
            role="group"
            aria-label={`${row.label}: ${formatPctPoints(row.drift / 100)} ${driftLabel}`}
          >
            <div className="compare-label" id={rowId}>{row.label}</div>
            <div className="compare-drift-track" aria-hidden="true">
              <div className="compare-drift-center" />
              {row.drift !== 0 && (
                <div
                  className={`compare-drift-bar ${isOver ? "over" : "under"}`}
                  style={{
                    width: `${barWidth}%`,
                    [isOver ? "left" : "right"]: "50%",
                  }}
                  title={`Drift ${row.drift > 0 ? "+" : ""}${row.drift.toFixed(1)}pp`}
                />
              )}
            </div>
            <div className="compare-meta">
              <span className={row.drift > 0 ? "is-over" : row.drift < 0 ? "is-under" : ""}>
                {formatPctPoints(row.drift / 100)}
              </span>
            </div>
          </div>
        );
      })}
      <div className="compare-legend" aria-hidden="true">
        <span><i className="swatch over" /> Overweight</span>
        <span><i className="swatch under" /> Underweight</span>
      </div>
    </div>
  );
}
