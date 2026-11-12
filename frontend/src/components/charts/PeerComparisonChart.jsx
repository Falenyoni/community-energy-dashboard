import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../ChartTooltip';

const PERIOD_WINDOW_DAYS = { day: 1, week: 7, month: 30 };

// "This site is the point, the peer group is context" -> emphasis form:
// one hue for the site, gray for everything else, per the data-viz skill.
export default function PeerComparisonChart({ siteSummary, comparison, period = 'day' }) {
  // "day" mode: comparison has one persisted row per date (period is an ISO
  // date string), so each day gets its own peer average. "week"/"month"
  // mode: the comparison endpoint instead returns a single on-the-fly row
  // for the whole window (period is a label like "week ending ..."), so
  // every visible day shares that one flat benchmark instead.
  const windowDays = PERIOD_WINDOW_DAYS[period] ?? 1;
  const visibleDays = period === 'day' ? siteSummary : siteSummary.slice(-windowDays);
  const comparisonByDate = new Map(comparison.map((c) => [c.period, c]));
  const flatPeerAverage = period === 'day' ? null : comparison[0]?.group_average_kwh ?? null;

  const rows = visibleDays.map((day) => ({
    date: day.date,
    this_site: day.total_kwh,
    peer_average: period === 'day' ? comparisonByDate.get(day.date)?.group_average_kwh ?? null : flatPeerAverage,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="date"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          tickLine={false}
          minTickGap={24}
        />
        <YAxis
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          width={40}
        />
        <Tooltip
          cursor={{ stroke: 'var(--baseline)', strokeWidth: 1 }}
          content={<ChartTooltip formatter={(v) => (v == null ? '—' : `${v.toFixed(2)} kWh`)} />}
        />
        <Line
          type="monotone"
          dataKey="peer_average"
          name="Community average"
          stroke="var(--text-muted)"
          strokeWidth={2}
          strokeDasharray="4 3"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="this_site"
          name="This house"
          stroke="var(--series-1)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 5 }}
        />
        <Legend wrapperStyle={{ fontSize: 12, color: 'var(--text-secondary)' }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
