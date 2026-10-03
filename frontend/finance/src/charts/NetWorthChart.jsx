import { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import Box from '@mui/material/Box';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import { lineOptions } from './common.js';
import { PALETTE } from '../format.js';

function computeProjection(series, monthsForward) {
  const first = new Date(series[0].date).getTime();
  const points = series.map((e) => [(new Date(e.date).getTime() - first) / 86400000, e.value]);
  const n = points.length;
  const sumX = points.reduce((s, p) => s + p[0], 0);
  const sumY = points.reduce((s, p) => s + p[1], 0);
  const sumXY = points.reduce((s, p) => s + p[0] * p[1], 0);
  const sumXX = points.reduce((s, p) => s + p[0] * p[0], 0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;

  const lastDate = new Date(series[n - 1].date);
  const projected = [];
  for (let m = 1; m <= monthsForward; m++) {
    const d = new Date(lastDate);
    d.setMonth(d.getMonth() + m);
    const x = (d.getTime() - first) / 86400000;
    projected.push({ date: d.toISOString().slice(0, 10), value: slope * x + intercept });
  }
  return projected;
}

export default function NetWorthChart({ netWorth, showProjection, onToggleProjection }) {
  const chartData = useMemo(() => {
    const projected = showProjection ? computeProjection(netWorth, 6) : [];
    const labels = [...netWorth.map((e) => e.date), ...projected.map((e) => e.date)];
    const datasets = [
      {
        label: 'Net worth',
        data: [...netWorth.map((e) => e.value), ...projected.map(() => null)],
        borderColor: PALETTE[0],
        backgroundColor: PALETTE[0] + '22',
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.15,
      },
    ];
    if (showProjection && netWorth.length) {
      const bridge = netWorth[netWorth.length - 1];
      datasets.push({
        label: 'Projected (linear trend)',
        // Nulls up to the last actual point, then the bridge value there so
        // the dashed line visually connects to where the solid line ends.
        data: [...netWorth.slice(0, -1).map(() => null), bridge.value, ...projected.map((e) => e.value)],
        borderColor: PALETTE[0],
        borderDash: [6, 4],
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
        tension: 0.15,
      });
    }
    return { labels, datasets };
  }, [netWorth, showProjection]);

  return (
    <Box>
      <FormControlLabel
        control={
          <Checkbox
            checked={showProjection}
            onChange={(e) => onToggleProjection(e.target.checked)}
            size="small"
          />
        }
        label="Show projection (simple linear trend, next 6 months)"
        sx={{ mb: 1 }}
      />
      <Box sx={{ height: 300 }}>
        <Line data={chartData} options={lineOptions({ legend: false })} />
      </Box>
    </Box>
  );
}
