import { useMemo, useState } from "react";
import { formatBrl, formatSignedBrl } from "../lib/format";
import { formatAxis, niceMax, numeric } from "../lib/chart";

export type ChartPoint = {
  month: number;
  label: string;
  value?: number | string;
  income?: number | string;
  expense?: number | string;
  balance?: number | string;
};

type MonthChartProps = {
  points: ChartPoint[];
  selectedMonth?: number | null;
  variant?: "summary" | "income" | "expense" | "neutral";
  onSelect: (month: number) => void;
};

export function MonthChart({ points, selectedMonth, variant = "neutral", onSelect }: MonthChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const width = 720;
  const height = variant === "summary" ? 236 : 200;
  const padL = 44;
  const padR = 12;
  const padT = 16;
  const padB = 28;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const band = innerW / Math.max(points.length, 1);

  const series = useMemo(() => {
    return points.map((point) => ({
      month: point.month,
      label: point.label,
      income: Math.max(0, numeric(point.income)),
      expense: Math.abs(numeric(point.expense ?? (variant === "expense" ? point.value : 0))),
      value: numeric(point.value),
      balance: numeric(point.balance ?? point.value),
    }));
  }, [points, variant]);

  const max = useMemo(() => {
    if (variant === "summary") {
      return niceMax(
        Math.max(
          1,
          ...series.map((point) => Math.max(point.income, point.expense, Math.abs(point.balance))),
        ),
      );
    }
    return niceMax(Math.max(1, ...series.map((point) => Math.abs(point.value))));
  }, [series, variant]);

  const zeroY = variant === "summary" ? padT + innerH * 0.52 : padT + innerH;
  const scale = variant === "summary" ? (innerH * 0.46) / max : innerH / max;
  const ticks = variant === "summary" ? [max, max / 2, 0, -max / 2, -max] : [max, max / 2, 0];

  const active = hover ?? selectedMonth ?? null;
  const activePoint = series.find((point) => point.month === active);

  return (
    <div className="chart-frame">
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Monthly chart">
        {ticks.map((tick) => {
          const y = variant === "summary" ? zeroY - tick * scale : padT + innerH - tick * scale;
          return (
            <g key={tick}>
              <line className="chart-grid" x1={padL} x2={width - padR} y1={y} y2={y} />
              <text className="chart-axis" x={padL - 6} y={y + 3} textAnchor="end">
                {formatAxis(tick)}
              </text>
            </g>
          );
        })}
        {series.map((point, index) => {
          const x = padL + index * band;
          const selected = selectedMonth === point.month;
          const hovered = hover === point.month;
          const cx = x + band / 2;
          const on = selected || hovered;
          if (variant === "summary") {
            const incomeH = point.income * scale;
            const expenseH = point.expense * scale;
            const barW = 11;
            const bx = cx - barW / 2;
            return (
              <g key={point.month}>
                <rect
                  className={`chart-bar income${on ? " is-on" : ""}`}
                  x={bx}
                  y={zeroY - incomeH}
                  width={barW}
                  height={Math.max(incomeH, 0)}
                  rx={2}
                />
                <rect
                  className={`chart-bar expense${on ? " is-on" : ""}`}
                  x={bx}
                  y={zeroY}
                  width={barW}
                  height={Math.max(expenseH, 0)}
                  rx={2}
                />
                <text className={`chart-label${selected ? " is-on" : ""}`} x={cx} y={height - 8} textAnchor="middle">
                  {point.label}
                </text>
                <rect
                  className="chart-hit"
                  x={x}
                  y={0}
                  width={band}
                  height={height}
                  onMouseEnter={() => setHover(point.month)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onSelect(point.month)}
                />
              </g>
            );
          }
          const value = Math.abs(point.value);
          const barH = value * scale;
          const negative = variant === "expense" || point.value < 0;
          return (
            <g key={point.month}>
              <rect
                className={`chart-bar ${negative ? "expense" : "income"}${on ? " is-on" : ""}`}
                x={x + band * 0.22}
                y={padT + innerH - barH}
                width={band * 0.56}
                height={Math.max(barH, 1.5)}
                rx={3}
              />
              <text className={`chart-label${selected ? " is-on" : ""}`} x={cx} y={height - 8} textAnchor="middle">
                {point.label}
              </text>
              <rect
                className="chart-hit"
                x={x}
                y={0}
                width={band}
                height={height}
                onMouseEnter={() => setHover(point.month)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelect(point.month)}
              />
            </g>
          );
        })}
        {variant === "summary"
          ? series.map((point, index, all) => {
              if (index === 0) return null;
              const prev = all[index - 1];
              const x1 = padL + (index - 0.5) * band;
              const x2 = padL + (index + 0.5) * band;
              return (
                <line
                  key={`line-${point.month}`}
                  className="chart-line"
                  x1={x1}
                  y1={zeroY - prev.balance * scale}
                  x2={x2}
                  y2={zeroY - point.balance * scale}
                />
              );
            })
          : null}
        {variant === "summary"
          ? series.map((point, index) => (
              <circle
                key={`dot-${point.month}`}
                className="chart-dot"
                cx={padL + (index + 0.5) * band}
                cy={zeroY - point.balance * scale}
                r={selectedMonth === point.month ? 3.6 : 2.4}
              />
            ))
          : null}
      </svg>
      <div className="chart-caption">
        {variant === "summary" ? (
          <div className="chart-legend">
            <span><i className="swatch income" /> Income</span>
            <span><i className="swatch expense" /> Expenses</span>
            <span><i className="swatch balance" /> Balance</span>
          </div>
        ) : (
          <span />
        )}
        <span className="chart-hover">
          {activePoint
            ? variant === "summary"
              ? `${activePoint.label}: in ${formatBrl(activePoint.income)} · out ${formatBrl(-activePoint.expense)} · ${formatSignedBrl(activePoint.balance)}`
              : `${activePoint.label}: ${formatBrl(activePoint.value)}`
            : "Click a month to filter"}
        </span>
      </div>
    </div>
  );
}
