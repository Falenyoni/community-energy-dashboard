import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../ChartTooltip';
import { channelFromDeviceId, CHANNEL_COLOR_VAR, cssVar } from '../../channelColors';

// Compare magnitude + tell channels apart -> bar chart, categorical color
// per channel (identity is the point: "which load dominates consumption").
export default function RankingChart({ data }) {
  const rows = data.map((d) => ({
    ...d,
    channel: channelFromDeviceId(d.device_id),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} layout="vertical" margin={{ top: 8, right: 24, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="var(--gridline)" horizontal={false} />
        <XAxis
          type="number"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-muted)', fontSize: 12 }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="device_id"
          stroke="var(--baseline)"
          tick={{ fill: 'var(--text-secondary)', fontSize: 12 }}
          tickLine={false}
          axisLine={false}
          width={140}
        />
        <Tooltip
          cursor={{ fill: 'var(--gridline)' }}
          content={<ChartTooltip formatter={(v) => `${v.toFixed(2)} kWh`} />}
        />
        <Bar dataKey="total_kwh" name="Total kWh" radius={[0, 4, 4, 0]}>
          {rows.map((row) => (
            <Cell key={row.device_id} fill={cssVar(CHANNEL_COLOR_VAR[row.channel] || '--series-1')} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
