import { useEffect, useState } from 'react';
import { getComparison, getSiteSummary, listSites } from '../api';

const STATUS_META = {
  above_average: { color: 'var(--status-warning)', label: 'Above average' },
  below_average: { color: 'var(--status-good)', label: 'Below average' },
  typical: { color: 'var(--text-muted)', label: 'Typical' },
  unknown: { color: 'var(--text-muted)', label: 'Not enough data' },
};

const PERIOD_WINDOW_DAYS = { day: 1, week: 7, month: 30 };
const PERIOD_COLUMN_LABEL = { day: "Today's kWh", week: 'Last 7 days kWh', month: 'Last 30 days kWh' };

export default function AdminOverview({ simRunning = false, period = 'day' }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    function load(showSpinner) {
      if (showSpinner) setLoading(true);
      const windowDays = PERIOD_WINDOW_DAYS[period];
      return listSites()
        .then((sites) =>
          Promise.all(
            sites.map((site) =>
              Promise.all([getSiteSummary(site.site_id), getComparison(site.site_id, period)])
                .then(([summary, comparison]) => {
                  // Sum (kWh) / max (peak kW) over the same trailing window
                  // the ranking and comparison endpoints use server-side.
                  const windowDays_ = summary.slice(-windowDays);
                  const totalKwh = windowDays_.length
                    ? windowDays_.reduce((sum, d) => sum + (d.total_kwh || 0), 0)
                    : null;
                  const peakKw = windowDays_.length
                    ? Math.max(...windowDays_.map((d) => d.peak_power_kw || 0))
                    : null;
                  // Last row with an actual ratio -- a stray future-dated
                  // test run can leave a chronologically-last row with
                  // ratio: null before its peers' data existed yet.
                  const latestComparison = [...comparison].reverse().find((c) => c.ratio != null);
                  return {
                    siteId: site.site_id,
                    label: site.anonymised_label,
                    totalKwh,
                    peakKw,
                    statusFlag: latestComparison?.status_flag ?? 'unknown',
                    ratio: latestComparison?.ratio ?? null,
                  };
                })
                .catch(() => ({
                  siteId: site.site_id,
                  label: site.anonymised_label,
                  totalKwh: null,
                  peakKw: null,
                  statusFlag: 'unknown',
                  ratio: null,
                }))
            )
          )
        )
        .then((results) => {
          if (cancelled) return;
          // Highest consumers first - the whole point of an admin view is spotting who to look at first.
          results.sort((a, b) => (b.totalKwh ?? -1) - (a.totalKwh ?? -1));
          setRows(results);
          setLoading(false);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err.message);
          setLoading(false);
        });
    }

    load(true);

    // While the community simulation runs, its periodic recompute changes
    // every household's DailySummary/ComparisonResult -- re-poll (no
    // spinner) so the ranking visibly reorders as the day streams in.
    const timer = simRunning ? setInterval(() => load(false), 2000) : null;

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [simRunning, period]);

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
              <th>{PERIOD_COLUMN_LABEL[period]}</th>
              <th>Peak kW</th>
              <th>vs. community average</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const statusMeta = STATUS_META[row.statusFlag] ?? STATUS_META.unknown;
              return (
                <tr key={row.siteId}>
                  <td>{row.label}</td>
                  <td>{row.totalKwh?.toFixed(2) ?? '-'}</td>
                  <td>{row.peakKw?.toFixed(2) ?? '-'}</td>
                  <td style={{ color: statusMeta.color }}>
                    {row.ratio != null ? `${(row.ratio * 100).toFixed(0)}% - ` : ''}
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
