import { useMemo, useState } from 'react';

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const SEQ_STEPS = ['--seq-100', '--seq-200', '--seq-300', '--seq-400', '--seq-500', '--seq-600', '--seq-700'];

// Compare magnitude across a grid -> heatmap, sequential single hue
// (blue), per the data-viz skill. Aggregated to day-of-week x hour-of-day
// (7x24) rather than raw calendar day x hour (30x24) -- a more legible,
// standard "usage pattern" view, and it matches the proposal's emphasis on
// weekday/weekend behaviour differing.
export default function HeatmapChart({ data }) {
  const [hovered, setHovered] = useState(null);

  const { grid, max } = useMemo(() => {
    const sums = Array.from({ length: 7 }, () => Array(24).fill(0));
    const counts = Array.from({ length: 7 }, () => Array(24).fill(0));

    data.forEach(({ date, hour, avg_power_kw }) => {
      const dow = (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7; // Mon=0..Sun=6
      sums[dow][hour] += avg_power_kw;
      counts[dow][hour] += 1;
    });

    const grid = sums.map((row, d) => row.map((sum, h) => (counts[d][h] ? sum / counts[d][h] : 0)));
    const max = Math.max(0.001, ...grid.flat());
    return { grid, max };
  }, [data]);

  const colorFor = (value) => {
    const step = Math.min(SEQ_STEPS.length - 1, Math.floor((value / max) * SEQ_STEPS.length));
    return `var(${SEQ_STEPS[step]})`;
  };

  return (
    <div className="heatmap">
      <div className="heatmap-grid">
        {grid.map((row, d) => (
          <div className="heatmap-row" key={DAY_LABELS[d]}>
            <span className="heatmap-row-label">{DAY_LABELS[d]}</span>
            {row.map((value, h) => (
              <div
                key={h}
                className="heatmap-cell"
                style={{ background: colorFor(value) }}
                onMouseEnter={() => setHovered({ day: DAY_LABELS[d], hour: h, value })}
                onMouseLeave={() => setHovered(null)}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="heatmap-hours">
        <span className="heatmap-row-label" aria-hidden="true" />
        {Array.from({ length: 24 }, (_, h) => (
          <span key={h} className="heatmap-hour-tick">
            {h % 6 === 0 ? h : ''}
          </span>
        ))}
      </div>
      <div className="heatmap-tooltip" role="status">
        {hovered
          ? `${hovered.day} ${String(hovered.hour).padStart(2, '0')}:00 — avg ${hovered.value.toFixed(3)} kW`
          : 'Hover a cell for the exact average power'}
      </div>
    </div>
  );
}
