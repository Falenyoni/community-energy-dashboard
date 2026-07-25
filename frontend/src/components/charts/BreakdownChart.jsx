import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../ChartTooltip';
import { CHANNEL_COLOR_VAR, CHANNEL_ORDER, cssVar } from '../../channelColors';

// Part-to-whole -> 100%-stacked horizontal bar, categorical color (same
// fixed mapping as the ranking chart, so a channel's color means the same
// thing everywhere on the page).
export default function BreakdownChart({ channelTotals }) {
  const total = CHANNEL_ORDER.reduce((sum, ch) => sum + (channelTotals[ch] || 0), 0) || 1;
  const row = { name: 'Today' };
  CHANNEL_ORDER.forEach((ch) => {
    row[ch] = channelTotals[ch] || 0;
  });

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={[row]} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <XAxis type="number" hide domain={[0, total]} />
        <YAxis type="category" dataKey="name" hide />
        <Tooltip
          cursor={{ fill: 'var(--gridline)' }}
          content={
            <ChartTooltip
              formatter={(v) => `${v.toFixed(2)} kWh (${((v / total) * 100).toFixed(0)}%)`}
            />
          }
        />
        {CHANNEL_ORDER.map((ch, i) => (
          <Bar
            key={ch}
            dataKey={ch}
            name={ch}
            stackId="today"
            fill={cssVar(CHANNEL_COLOR_VAR[ch])}
            radius={i === 0 ? [4, 0, 0, 4] : i === CHANNEL_ORDER.length - 1 ? [0, 4, 4, 0] : 0}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
