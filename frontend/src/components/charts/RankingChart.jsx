import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../ChartTooltip';
import { channelFromDeviceId, CHANNEL_COLOR_VAR, cssVar } from '../../channelColors';

// Total kWh (energy, channel-colored — identity is the point: "which load
// dominates consumption") and peak kW (power, one flat color — a different
// question: "which load hits the hardest," even briefly) sit on separate
// value axes since kWh and kW aren't the same scale or the same quantity.
function formatRankingValue(value, dataKey) {
  if (value == null) return '—';
  return dataKey === 'peak_power_kw' ? `${value.toFixed(2)} kW` : `${value.toFixed(2)} kWh`;
}

export default function RankingChart({ data }) {
  const rows = data.map((d) => ({
    ...d,
    channel: channelFromDeviceId(d.device_id),
    displayLabel: d.device_id.replace(/^SITE-/, 'HOUSE-'),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="var(--gridline)" horizontal={false} />
        <XAxis
          xAxisId="energy"
          type="number"
          orientation="bottom"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          tickLine={false}
          label={{ value: 'Total energy (kWh)', position: 'insideBottom', offset: -4, fill: 'var(--text-muted)', fontSize: 11 }}
        />
        <XAxis
          xAxisId="power"
          type="number"
          orientation="top"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          tickLine={false}
          label={{ value: 'Peak power (kW)', position: 'insideTop', offset: -4, fill: 'var(--text-muted)', fontSize: 11 }}
        />
        <YAxis
          type="category"
          dataKey="displayLabel"
          xAxisId="energy"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          width={140}
        />
        <Tooltip
          cursor={{ fill: 'var(--gridline)' }}
          content={<ChartTooltip formatter={formatRankingValue} />}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar xAxisId="energy" dataKey="total_kwh" name="Total energy" radius={[0, 4, 4, 0]}>
          {rows.map((row) => (
            <Cell key={row.device_id} fill={cssVar(CHANNEL_COLOR_VAR[row.channel] || '--series-1')} />
          ))}
        </Bar>
        <Bar
          xAxisId="power"
          dataKey="peak_power_kw"
          name="Peak power"
          fill={cssVar('--text-muted')}
          radius={[0, 4, 4, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
