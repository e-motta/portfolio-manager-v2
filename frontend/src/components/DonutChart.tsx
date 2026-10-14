import { formatCompactBrl } from "../lib/format";
import { sliceColor } from "../lib/chart";

type Slice = {
  label: string;
  value: number;
};

type PreparedSlice = Slice & { key: string };

type DonutChartProps = {
  slices: Slice[];
  centerLabel?: string;
  centerValue?: string;
};

const MAX_SLICES = 10;
const MIN_PCT_THRESHOLD = 0.02;
const GROUPED_OUTROS_KEY = "__grouped_outros__";

function prepareSlices(slices: Slice[], total: number): PreparedSlice[] {
  if (total <= 0) return [];

  const sorted = [...slices]
    .map((s) => ({ ...s, value: Math.max(0, s.value) }))
    .filter((s) => s.value > 0)
    .sort((a, b) => b.value - a.value);

  const significant: PreparedSlice[] = [];
  let otherValue = 0;

  for (const slice of sorted) {
    const pct = slice.value / total;
    if (pct < MIN_PCT_THRESHOLD || significant.length >= MAX_SLICES - 1) {
      otherValue += slice.value;
    } else {
      significant.push({ ...slice, key: slice.label });
    }
  }

  if (otherValue > 0) {
    significant.push({ label: "Outros", value: otherValue, key: GROUPED_OUTROS_KEY });
  }

  return significant;
}

function buildAriaLabel(slices: Slice[], total: number, centerLabel: string): string {
  if (total <= 0 || slices.length === 0) {
    return `${centerLabel}: sem dados`;
  }
  const parts = slices
    .slice(0, 5)
    .map((s) => `${s.label} ${((s.value / total) * 100).toFixed(0)}%`);
  const suffix = slices.length > 5 ? ` e mais ${slices.length - 5}` : "";
  return `${centerLabel}: ${parts.join(", ")}${suffix}`;
}

export function DonutChart({ slices, centerLabel = "Total", centerValue }: DonutChartProps) {
  const total = slices.reduce((sum, slice) => sum + Math.max(0, slice.value), 0);
  const prepared = prepareSlices(slices, total);

  const size = 168;
  const radius = 58;
  const stroke = 18;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * radius;
  let offset = 0;

  const ariaLabel = buildAriaLabel(prepared, total, centerLabel);

  return (
    <div className="donut">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="donut-svg"
        role="img"
        aria-label={ariaLabel}
      >
        <circle cx={cx} cy={cy} r={radius} fill="none" stroke="var(--paper-2)" strokeWidth={stroke} />
        {total > 0
          ? prepared.map((slice, index) => {
              const frac = slice.value / total;
              const dash = circ * frac;
              const node = (
                <circle
                  key={slice.key}
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
        {prepared.map((slice, index) => {
          const pct = total > 0 ? (slice.value / total) * 100 : 0;
          return (
            <li key={slice.key}>
              <i style={{ background: sliceColor(index) }} />
              <span>{slice.label}</span>
              <strong>
                {total > 0 ? `${pct.toFixed(1)}% · ${formatCompactBrl(slice.value)}` : "—"}
              </strong>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
