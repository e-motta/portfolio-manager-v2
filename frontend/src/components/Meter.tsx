type MeterProps = {
  value: number;
  max: number;
  label?: string;
  accessibleLabel?: string;
};

export function Meter({ value, max, label, accessibleLabel }: MeterProps) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const meterLabel = accessibleLabel || label || `${pct.toFixed(0)}% of ${max}`;

  return (
    <div
      className="meter"
      role="meter"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={meterLabel}
    >
      <div className="meter-track" aria-hidden="true">
        <div className="meter-fill" style={{ width: `${pct}%` }} />
      </div>
      {label ? <div className="meter-label">{label}</div> : null}
    </div>
  );
}
