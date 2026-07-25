import { Line, LineChart, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import ChartTooltip from '../ChartTooltip';

// Trend over time -> line, sequential single hue (blue), per the data-viz
// skill's job->form mapping. Single series, so no legend needed (the
// chart title names it).
export default function TrendChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
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
          content={<ChartTooltip formatter={(v) => `${v.toFixed(2)} kWh`} />}
        />
        <Line
          type="monotone"
          dataKey="total_kwh"
          name="Daily consumption"
          stroke="var(--seq-500)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
