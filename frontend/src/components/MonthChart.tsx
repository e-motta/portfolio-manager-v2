import { asNumber } from "../lib/format";

type Point = {
  month: number;
  label: string;
  value?: number | string;
  income?: number | string;
  expense?: number | string;
  balance?: number | string;
};

type MonthChartProps = {
  points: Point[];
  selectedMonth?: number | null;
  variant?: string;
  onSelect: (month: number) => void;
};

export function MonthChart({ points, selectedMonth, variant, onSelect }: MonthChartProps) {
  const values = points.map((point) => {
    if (variant === "summary") return Math.abs(asNumber(point.balance));
    return Math.abs(asNumber(point.value));
  });
  const max = Math.max(1, ...values);

  return (
    <div className="chart" aria-hidden="false">
      {points.map((point, index) => {
        const value = values[index];
        const height = `${Math.max(4, (value / max) * 100)}%`;
        const active = selectedMonth === point.month;
        return (
          <button
            type="button"
            key={point.month}
            onClick={() => onSelect(point.month)}
            title={point.label}
          >
            <span
              className={`bar${variant === "expense" ? " expense" : ""}${active ? " is-active" : ""}`}
              style={{ height }}
            />
            <span>{point.label}</span>
          </button>
        );
      })}
    </div>
  );
}
