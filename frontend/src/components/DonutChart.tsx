import { formatCompactBrl } from "../lib/format";
import { sliceColor } from "../lib/chart";

type Slice = {
  label: string;
  value: number;
};

type DonutChartProps = {
  slices: Slice[];
  centerLabel?: string;
  centerValue?: string;
};

export function DonutChart({ slices, centerLabel = "Total", centerValue }: DonutChartProps) {
  const total = slices.reduce((sum, slice) => sum + Math.max(0, slice.value), 0);
  const size = 168;
  const radius = 58;
  const stroke = 18;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * radius;
  let offset = 0;

  return (
    <div className="donut">
      <svg viewBox={`0 0 ${size} ${size}`} className="donut-svg" aria-hidden="true">
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="var(--paper-2)" strokeWidth={stroke} />
        {total > 0
          ? slices.map((slice, index) => {
              const frac = Math.max(0, slice.value) / total;
              const dash = circ * frac;
              const node = (
                <circle
                  key={slice.label}
                  cx={cx}
                  cy={cy}
                  r={radius}
                  fill="none"
                  stroke={sliceColor(index)}
                  strokeWidth={stroke}
                  strokeDasharray={`${dash} ${circ - dash}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="butt"
                  transform={`rotate(-90 ${cx} ${cy})`}
                />
              );
              offset += dash;
              return node;
            })
          : null}
        <text className="donut-center-value" x={cx} y={cy - 2} textAnchor="middle">
          {centerValue || formatCompactBrl(total)}
        </text>
        <text className="donut-center-label" x={cx} y={cy + 14} textAnchor="middle">
          {centerLabel}
        </text>
      </svg>
      <ul className="donut-legend">
        {slices.map((slice, index) => (
          <li key={slice.label}>
            <i style={{ background: sliceColor(index) }} />
            <span>{slice.label}</span>
            <strong>{total ? `${((Math.max(0, slice.value) / total) * 100).toFixed(0)}%` : "—"}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}
