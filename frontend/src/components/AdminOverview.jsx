import { useEffect, useState } from 'react';
import { getComparison, getSiteSummary, listSites } from '../api';

const STATUS_META = {
  above_average: { color: 'var(--status-warning)', label: 'Above average' },
  below_average: { color: 'var(--status-good)', label: 'Below average' },
  typical: { color: 'var(--text-muted)', label: 'Typical' },
  unknown: { color: 'var(--text-muted)', label: 'Not enough data' },
};

export default function AdminOverview() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    listSites()
      .then((sites) =>
        Promise.all(
          sites.map((site) =>
            Promise.all([getSiteSummary(site.site_id), getComparison(site.site_id)])
              .then(([summary, comparison]) => {
                const latestDay = summary.at(-1);
                const latestComparison = comparison.at(-1);
                return {
                  siteId: site.site_id,
                  label: site.anonymised_label,
                  totalKwh: latestDay?.total_kwh ?? null,
                  peakKw: latestDay?.peak_power_kw ?? null,
                  cost: latestDay?.cost_estimate ?? null,
                  statusFlag: latestComparison?.status_flag ?? 'unknown',
                  ratio: latestComparison?.ratio ?? null,
                };
              })
              .catch(() => ({
                siteId: site.site_id,
                label: site.anonymised_label,
                totalKwh: null,
                peakKw: null,
                cost: null,
                statusFlag: 'unknown',
                ratio: null,
              }))
          )
        )
      )
      .then((results) => {
        if (cancelled) return;
        // Highest consumers first — the whole point of an admin view is spotting who to look at first.
        results.sort((a, b) => (b.totalKwh ?? -1) - (a.totalKwh ?? -1));
        setRows(results);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <p className="dashboard-loading">Loading community overview...</p>;
  if (error) return <p className="dashboard-loading">Failed to load overview: {error}</p>;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Admin: All Households</h1>
      </header>

      <section className="chart-card">
        <table className="admin-overview-table">
          <thead>
            <tr>
              <th>Household</th>
              <th>Today's kWh</th>
              <th>Peak kW</th>
              <th>Estimated cost</th>
              <th>vs. community average</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const statusMeta = STATUS_META[row.statusFlag] ?? STATUS_META.unknown;
              return (
                <tr key={row.siteId}>
                  <td>{row.label}</td>
                  <td>{row.totalKwh?.toFixed(2) ?? '—'}</td>
                  <td>{row.peakKw?.toFixed(2) ?? '—'}</td>
                  <td>{row.cost != null ? `R${row.cost.toFixed(2)}` : '—'}</td>
                  <td style={{ color: statusMeta.color }}>
                    {row.ratio != null ? `${(row.ratio * 100).toFixed(0)}% — ` : ''}
                    {statusMeta.label}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
