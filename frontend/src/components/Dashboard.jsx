import { useEffect, useMemo, useState } from 'react';
import { getComparison, getDeviceDailySummary, getHeatmap, getRanking, getSiteSummary, listSites } from '../api';
import { CHANNEL_COLOR_VAR, CHANNEL_ORDER, cssVar } from '../channelColors';
import StatTile from './StatTile';
import TrendChart from './charts/TrendChart';
import RankingChart from './charts/RankingChart';
import PeerComparisonChart from './charts/PeerComparisonChart';
import BreakdownChart from './charts/BreakdownChart';
import HeatmapChart from './charts/HeatmapChart';

const STATUS_META = {
  above_average: { color: 'var(--status-warning)', label: 'Above community average' },
  below_average: { color: 'var(--status-good)', label: 'Below community average' },
  typical: { color: 'var(--text-muted)', label: 'Typical for the community' },
  unknown: { color: 'var(--text-muted)', label: 'Not enough data yet' },
};

function downloadCsv(rows, filename) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(','), ...rows.map((r) => headers.map((h) => r[h]).join(','))].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function downloadPdf({ siteLabel, latestDay, latestComparison, statusMeta, rows, filename }) {
  // Dynamically imported (not a top-level import) so jsPDF's ~200KB dependency
  // tree only loads when someone actually clicks "Export PDF", not on every
  // page load.
  const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
    import('jspdf'),
    import('jspdf-autotable'),
  ]);

  const doc = new jsPDF();

  doc.setFontSize(16);
  doc.text('Community Energy Dashboard', 14, 18);
  doc.setFontSize(10);
  doc.setTextColor(100);
  doc.text(`Site: ${siteLabel}`, 14, 25);
  doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 30);

  doc.setFontSize(12);
  doc.setTextColor(0);
  doc.text('Summary', 14, 40);
  doc.setFontSize(10);
  const kpiLines = [
    `Today's consumption: ${latestDay?.total_kwh?.toFixed(2) ?? '-'} kWh`,
    `Peak power: ${latestDay?.peak_power_kw?.toFixed(2) ?? '-'} kW`,
    `Estimated cost: R${latestDay?.cost_estimate?.toFixed(2) ?? '-'}`,
    `Community comparison: ${latestComparison?.ratio ? `${(latestComparison.ratio * 100).toFixed(0)}%` : '-'} (${statusMeta.label})`,
  ];
  kpiLines.forEach((line, i) => doc.text(line, 14, 47 + i * 6));

  const tableStartY = 47 + kpiLines.length * 6 + 6;
  doc.setFontSize(12);
  doc.text('Daily summary', 14, tableStartY - 4);

  autoTable(doc, {
    startY: tableStartY,
    head: [['Date', 'Total kWh', 'Peak kW', 'Cost estimate (R)']],
    body: rows.map((r) => [
      r.date,
      r.total_kwh?.toFixed?.(2) ?? r.total_kwh,
      r.peak_power_kw?.toFixed?.(2) ?? r.peak_power_kw,
      r.cost_estimate?.toFixed?.(2) ?? r.cost_estimate,
    ]),
    styles: { fontSize: 9 },
    headStyles: { fillColor: [51, 102, 153] },
  });

  doc.save(filename);
}

export default function Dashboard() {
  const [sites, setSites] = useState([]);
  const [siteId, setSiteId] = useState('');
  const [siteSummary, setSiteSummary] = useState([]);
  const [ranking, setRanking] = useState([]);
  const [comparison, setComparison] = useState([]);
  const [heatmap, setHeatmap] = useState([]);
  const [channelTotals, setChannelTotals] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listSites().then((rows) => {
      setSites(rows);
      if (rows.length) setSiteId(rows[0].site_id);
    });
  }, []);

  useEffect(() => {
    if (!siteId) return;
    setLoading(true);

    Promise.all([
      getSiteSummary(siteId),
      getRanking(siteId),
      getComparison(siteId),
      getHeatmap(siteId),
      Promise.all(
        CHANNEL_ORDER.map((ch) =>
          getDeviceDailySummary(`${siteId}-${ch.toUpperCase()}`)
            .then((rows) => [ch, rows.at(-1)?.total_kwh || 0])
            .catch(() => [ch, 0])
        )
      ),
    ]).then(([summary, rank, comp, heat, channelPairs]) => {
      setSiteSummary(summary);
      setRanking(rank);
      setComparison(comp);
      setHeatmap(heat);
      setChannelTotals(Object.fromEntries(channelPairs));
      setLoading(false);
    });
  }, [siteId]);

  const latestDay = siteSummary.at(-1);
  const latestComparison = comparison.at(-1);
  const statusMeta = STATUS_META[latestComparison?.status_flag] ?? STATUS_META.unknown;
  const siteLabel = sites.find((s) => s.site_id === siteId)?.anonymised_label ?? siteId;

  const csvRows = useMemo(
    () => siteSummary.map((d) => ({ date: d.date, total_kwh: d.total_kwh, peak_power_kw: d.peak_power_kw, cost_estimate: d.cost_estimate })),
    [siteSummary]
  );

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Community Energy Dashboard</h1>
        <div className="dashboard-controls">
          <label htmlFor="site-select">House</label>
          <select id="site-select" value={siteId} onChange={(e) => setSiteId(e.target.value)}>
            {sites.map((s) => (
              <option key={s.site_id} value={s.site_id}>
                {s.anonymised_label}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => downloadCsv(csvRows, `${siteId}-daily-summary.csv`)}>
            Export CSV
          </button>
          <button
            type="button"
            onClick={() =>
              downloadPdf({
                siteLabel,
                latestDay,
                latestComparison,
                statusMeta,
                rows: csvRows,
                filename: `${siteId}-daily-summary.pdf`,
              })
            }
          >
            Export PDF
          </button>
        </div>
      </header>

      {loading ? (
        <p className="dashboard-loading">Loading...</p>
      ) : (
        <>
          <section className="kpi-row">
            <StatTile label="Today's consumption" value={latestDay?.total_kwh.toFixed(2) ?? '—'} unit="kWh" />
            <StatTile label="Peak power" value={latestDay?.peak_power_kw?.toFixed(2) ?? '—'} unit="kW" />
            <StatTile label="Estimated cost" value={`R${latestDay?.cost_estimate?.toFixed(2) ?? '—'}`} />
            <StatTile
              label="Community comparison"
              value={latestComparison?.ratio ? `${(latestComparison.ratio * 100).toFixed(0)}%` : '—'}
              statusColor={statusMeta.color}
              statusLabel={statusMeta.label}
            />
          </section>

          <section className="chart-card">
            <h2>Daily consumption trend</h2>
            <TrendChart data={siteSummary} />
          </section>

          <div className="chart-grid">
            <section className="chart-card">
              <h2>Device ranking</h2>
              <RankingChart data={ranking} />
            </section>

            <section className="chart-card">
              <h2>vs. community average</h2>
              <PeerComparisonChart siteSummary={siteSummary} comparison={comparison} />
            </section>
          </div>

          <section className="chart-card">
            <h2>Today's breakdown by channel</h2>
            <BreakdownChart channelTotals={channelTotals} />
            <div className="legend-row">
              {CHANNEL_ORDER.map((ch) => (
                <span key={ch} className="legend-item">
                  <span className="legend-dot" style={{ background: cssVar(CHANNEL_COLOR_VAR[ch]) }} />
                  {ch}
                </span>
              ))}
            </div>
          </section>

          <section className="chart-card">
            <h2>Hourly usage pattern</h2>
            <HeatmapChart data={heatmap} />
          </section>
        </>
      )}
    </div>
  );
}
