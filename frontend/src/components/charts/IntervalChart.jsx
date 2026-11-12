import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../ChartTooltip';
import { CHANNEL_COLOR_VAR, CHANNEL_ORDER, cssVar } from '../../channelColors';

// Within-day load shape -> multi-line, categorical color (same fixed
// per-channel mapping as the breakdown and ranking charts), one point per
// 15-minute reading rather than per-day or per-hour-averaged.
export default function IntervalChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--gridline)" vertical={false} />
        <XAxis
          dataKey="time"
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
          content={<ChartTooltip formatter={(v) => `${v.toFixed(3)} kW`} />}
        />
        {CHANNEL_ORDER.map((ch) => (
          <Line
            key={ch}
            type="monotone"
            dataKey={ch}
            name={ch}
            stroke={cssVar(CHANNEL_COLOR_VAR[ch])}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
