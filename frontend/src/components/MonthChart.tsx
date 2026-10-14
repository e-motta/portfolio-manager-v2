import { useMemo, useState, useRef, useEffect, useCallback, useId } from "react";
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

const SHORT_LABELS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

function hasData(point: { income: number; expense: number; value: number }): boolean {
  return point.income > 0 || point.expense > 0 || point.value !== 0;
}

export function MonthChart({ points, selectedMonth, variant = "neutral", onSelect }: MonthChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(720);
  const [hover, setHover] = useState<number | null>(null);
  const [tapped, setTapped] = useState<number | null>(null);
  const isTouch = typeof window !== "undefined" && "ontouchstart" in window;
  const chartId = useId();
  const descId = `${chartId}-desc`;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width || 720;
      setContainerWidth(width);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const isPhone = containerWidth < 500;
  const width = isPhone ? 360 : 720;
  const height = variant === "summary" ? (isPhone ? 180 : 236) : (isPhone ? 160 : 200);
  const padL = isPhone ? 36 : 44;
  const padR = isPhone ? 8 : 12;
  const padT = 16;
  const padB = isPhone ? 24 : 28;
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

  const lastDataIndex = useMemo(() => {
    for (let i = series.length - 1; i >= 0; i--) {
      if (hasData(series[i])) return i;
    }
    return -1;
  }, [series]);

  const { posMax, negMax } = useMemo(() => {
    if (variant === "summary") {
      const positives = series.map((p) => Math.max(p.income, p.balance > 0 ? p.balance : 0));
      const negatives = series.map((p) => Math.max(p.expense, p.balance < 0 ? Math.abs(p.balance) : 0));
      return {
        posMax: niceMax(Math.max(1, ...positives)),
        negMax: niceMax(Math.max(1, ...negatives)),
      };
    }
    const max = niceMax(Math.max(1, ...series.map((point) => Math.abs(point.value))));
    return { posMax: max, negMax: max };
  }, [series, variant]);

  const posHeight = variant === "summary" ? innerH * (posMax / (posMax + negMax)) : innerH;
  const negHeight = variant === "summary" ? innerH - posHeight : 0;
  const zeroY = padT + posHeight;
  const posScale = posHeight / posMax;
  const negScale = negHeight / negMax;

  const posTicks = isPhone
    ? [posMax, 0]
    : [posMax, posMax / 2, 0];
  const negTicks = variant === "summary"
    ? (isPhone ? [-negMax] : [-negMax / 2, -negMax])
    : [];
  const ticks = [...posTicks, ...negTicks];

  const active = tapped ?? hover ?? selectedMonth ?? null;
  const activePoint = series.find((point) => point.month === active);

  const handleClick = useCallback((month: number) => {
    if (isTouch) {
      setTapped(month);
    }
    onSelect(month);
  }, [isTouch, onSelect]);

  const chartDescription = useMemo(() => {
    if (variant === "summary") {
      return `Monthly financial chart showing income, expenses, and balance for ${series.length} months.`;
    }
    const label = variant === "expense" ? "expenses" : variant === "income" ? "income" : "values";
    return `Monthly ${label} chart for ${series.length} months.`;
  }, [series.length, variant]);

  return (
    <div className="chart-frame" ref={containerRef}>
      <p id={descId} className="sr-only">{chartDescription}</p>
      <svg
        className="chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={variant === "summary" ? "Monthly income, expense and balance chart" : `Monthly ${variant} chart`}
        aria-describedby={descId}
        style={{ minHeight: isPhone ? "180px" : undefined }}
      >
        {ticks.map((tick) => {
          const y = tick >= 0
            ? zeroY - tick * posScale
            : zeroY + Math.abs(tick) * negScale;
          return (
            <g key={tick}>
              <line className="chart-grid" x1={padL} x2={width - padR} y1={y} y2={y} />
              <text
                className="chart-axis"
                x={padL - 6}
                y={y + 3}
                textAnchor="end"
                style={{ fontSize: isPhone ? "9px" : undefined }}
              >
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
          const on = selected || hovered || tapped === point.month;
          const displayLabel = isPhone ? SHORT_LABELS[point.month - 1] || point.label : point.label;
          if (variant === "summary") {
            const incomeH = point.income * posScale;
            const expenseH = point.expense * negScale;
            const barW = isPhone ? 8 : 11;
            const bx = cx - barW / 2;
            return (
              <g key={point.month}>
                <rect
                  className={`chart-bar income${on ? " is-on" : ""}`}
                  x={bx}
                  y={zeroY - Math.max(incomeH, point.income > 0 ? 2 : 0)}
                  width={barW}
                  height={Math.max(incomeH, point.income > 0 ? 2 : 0)}
                  rx={2}
                />
                <rect
                  className={`chart-bar expense${on ? " is-on" : ""}`}
                  x={bx}
                  y={zeroY}
                  width={barW}
                  height={Math.max(expenseH, point.expense > 0 ? 2 : 0)}
                  rx={2}
                />
                <text
                  className={`chart-label${selected ? " is-on" : ""}`}
                  x={cx}
                  y={height - (isPhone ? 6 : 8)}
                  textAnchor="middle"
                  style={{ fontSize: isPhone ? "9px" : undefined }}
                >
                  {displayLabel}
                </text>
              </g>
            );
          }
          const value = Math.abs(point.value);
          const barH = value * posScale;
          const negative = variant === "expense" || point.value < 0;
          return (
            <g key={point.month}>
              <rect
                className={`chart-bar ${negative ? "expense" : "income"}${on ? " is-on" : ""}`}
                x={x + band * 0.22}
                y={padT + posHeight - barH}
                width={band * 0.56}
                height={Math.max(barH, 1.5)}
                rx={3}
              />
              <text
                className={`chart-label${selected ? " is-on" : ""}`}
                x={cx}
                y={height - (isPhone ? 6 : 8)}
                textAnchor="middle"
                style={{ fontSize: isPhone ? "9px" : undefined }}
              >
                {displayLabel}
              </text>
            </g>
          );
        })}
        {variant === "summary"
          ? series.map((point, index, all) => {
              if (index === 0) return null;
              if (index > lastDataIndex) return null;
              const prev = all[index - 1];
              const x1 = padL + (index - 0.5) * band;
              const x2 = padL + (index + 0.5) * band;
              const y1 = prev.balance >= 0
                ? zeroY - prev.balance * posScale
                : zeroY + Math.abs(prev.balance) * negScale;
              const y2 = point.balance >= 0
                ? zeroY - point.balance * posScale
                : zeroY + Math.abs(point.balance) * negScale;
              return (
                <line
                  key={`line-${point.month}`}
                  className="chart-line"
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                />
              );
            })
          : null}
        {variant === "summary"
          ? series.map((point, index) => {
              if (index > lastDataIndex) return null;
              const cy = point.balance >= 0
                ? zeroY - point.balance * posScale
                : zeroY + Math.abs(point.balance) * negScale;
              return (
                <circle
                  key={`dot-${point.month}`}
                  className="chart-dot"
                  cx={padL + (index + 0.5) * band}
                  cy={cy}
                  r={selectedMonth === point.month ? 3.6 : 2.4}
                />
              );
            })
          : null}
        {series.map((point, index) => {
          const x = padL + index * band;
          const barLabel = variant === "summary"
            ? `${point.label}: income ${formatBrl(point.income)}, expenses ${formatBrl(point.expense)}, balance ${formatSignedBrl(point.balance)}`
            : `${point.label}: ${formatBrl(Math.abs(point.value))}`;
          return (
            <rect
              key={`hit-${point.month}`}
              className="chart-hit"
              x={x}
              y={0}
              width={band}
              height={height}
              fill="#000"
              fillOpacity={0}
              pointerEvents="all"
              tabIndex={0}
              role="button"
              aria-label={barLabel}
              onMouseEnter={() => setHover(point.month)}
              onMouseLeave={() => setHover(null)}
              onClick={() => handleClick(point.month)}
              onFocus={() => setHover(point.month)}
              onBlur={() => setHover(null)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleClick(point.month);
                }
              }}
            />
          );
        })}
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
            : isTouch ? "Tap a month" : "Select a month to filter"}
        </span>
      </div>
    </div>
  );
}
