import { formatAxis } from "../lib/chart";
import { formatBrl } from "../lib/format";

type SparklineProps = {
  values: number[];
  labels?: string[];
};

export function Sparkline({ values, labels }: SparklineProps) {
  if (values.length < 2) return null;
  const width = 720;
  const height = 140;
  const padL = 44;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;
  const points = values.map((value, index) => {
    const x = padL + (index / (values.length - 1)) * innerW;
    const y = padT + innerH - ((value - min) / span) * innerH;
    return { x, y, value };
  });
  const d = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
  const area = `${d} L ${points[points.length - 1].x} ${padT + innerH} L ${points[0].x} ${padT + innerH} Z`;

  return (
    <div className="chart-frame">
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Value over time">
        <line className="chart-grid" x1={padL} x2={width - padR} y1={padT} y2={padT} />
        <line className="chart-grid" x1={padL} x2={width - padR} y1={padT + innerH / 2} y2={padT + innerH / 2} />
        <line className="chart-grid" x1={padL} x2={width - padR} y1={padT + innerH} y2={padT + innerH} />
        <text className="chart-axis" x={padL - 6} y={padT + 3} textAnchor="end">{formatAxis(max)}</text>
        <text className="chart-axis" x={padL - 6} y={padT + innerH + 3} textAnchor="end">{formatAxis(min)}</text>
        <path className="spark-area" d={area} />
        <path className="spark-line" d={d} />
        {points.map((point, index) => (
          <circle key={index} className="chart-dot" cx={point.x} cy={point.y} r={2.6}>
            <title>{`${labels?.[index] || ""} ${formatBrl(point.value)}`}</title>
          </circle>
        ))}
        {labels?.length
          ? [0, values.length - 1].map((index) => (
              <text key={index} className="chart-label" x={points[index].x} y={height - 6} textAnchor={index === 0 ? "start" : "end"}>
                {labels[index]}
              </text>
            ))
          : null}
      </svg>
    </div>
  );
}
