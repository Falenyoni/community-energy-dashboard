export default function ChartTooltip({ active, payload, label, formatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="chart-tooltip-row">
          <span className="chart-tooltip-swatch" style={{ background: entry.color }} aria-hidden="true" />
          <span>{entry.name}</span>
          <strong>{formatter ? formatter(entry.value, entry.dataKey) : entry.value}</strong>
        </div>
      ))}
    </div>
  );
}
