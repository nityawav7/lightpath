interface Props {
  values: number[];
  height?: number;
  color?: string;
  threshold?: number;
  min?: number;
  max?: number;
  label: string;
  unit: string;
}

export function Sparkline({ values, height = 54, color = "var(--accent)", threshold, label, unit, ...r }: Props) {
  const w = 260;
  const last = values.at(-1);
  if (values.length < 2) {
    return (
      <div className="spark">
        <div className="spark-head">
          <span>{label}</span>
          <strong>{last !== undefined ? `${last.toFixed(1)} ${unit}` : "—"}</strong>
        </div>
        <div className="spark-empty">collecting samples…</div>
      </div>
    );
  }
  const lo = Math.min(r.min ?? Infinity, ...values, threshold ?? Infinity);
  const hi = Math.max(r.max ?? -Infinity, ...values, threshold ?? -Infinity);
  const span = hi - lo || 1;
  const y = (v: number) => height - 4 - ((v - lo) / span) * (height - 8);
  const x = (i: number) => (i / (values.length - 1)) * w;
  const pts = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const breach = threshold !== undefined && last !== undefined && last < threshold;
  return (
    <div className="spark">
      <div className="spark-head">
        <span>{label}</span>
        <strong className={breach ? "text-crit" : undefined}>
          {last!.toFixed(1)} {unit}
        </strong>
      </div>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        {threshold !== undefined && (
          <line x1={0} x2={w} y1={y(threshold)} y2={y(threshold)} className="spark-threshold" />
        )}
        <polyline points={`0,${height} ${pts} ${w},${height}`} fill={color} opacity={0.12} />
        <polyline points={pts} fill="none" stroke={breach ? "var(--crit)" : color} strokeWidth={2} />
      </svg>
    </div>
  );
}
