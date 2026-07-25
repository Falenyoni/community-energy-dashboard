export default function StatTile({ label, value, unit, statusColor, statusLabel }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile-label">{label}</div>
      <div className="stat-tile-value">
        {value}
        {unit && <span className="stat-tile-unit">{unit}</span>}
      </div>
      {statusLabel && (
        <div className="stat-tile-status">
          <span className="status-dot" style={{ background: statusColor }} aria-hidden="true" />
          {statusLabel}
        </div>
      )}
    </div>
  );
}
