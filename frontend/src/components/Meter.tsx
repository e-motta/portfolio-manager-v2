type MeterProps = {
  value: number;
  max: number;
  label?: string;
};

export function Meter({ value, max, label }: MeterProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return (
    <div className="meter">
      <div className="meter-track" aria-hidden="true">
        <div className="meter-fill" style={{ width: `${pct}%` }} />
      </div>
      {label ? <div className="meter-label">{label}</div> : null}
    </div>
  );
}
