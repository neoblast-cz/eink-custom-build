import { Line } from 'react-chartjs-2';
import Box from '@mui/material/Box';
import { lineOptions } from './common.js';
import { PALETTE } from '../format.js';

// Generic multi-series line/area chart driven by an array of
// {date, [key]: number} rows — used for allocation-over-time, cumulative
// interest by institution, holdings capital invested over time, and (with
// a single key) the per-category mini value charts.
export default function MultiSeriesLineChart({
  data,
  seriesKeys,
  seriesLabels = {},
  stacked = false,
  fill = true,
  height = 300,
  legend = true,
}) {
  const chartData = {
    labels: data.map((e) => e.date),
    datasets: seriesKeys.map((key, i) => ({
      label: seriesLabels[key] || key,
      data: data.map((e) => e[key] || 0),
      borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: fill ? PALETTE[i % PALETTE.length] + '33' : PALETTE[i % PALETTE.length],
      fill,
      pointRadius: 0,
      borderWidth: fill ? 1 : 2,
      tension: 0.15,
    })),
  };
  return (
    <Box sx={{ height }}>
      <Line data={chartData} options={lineOptions({ stacked, legend })} />
    </Box>
  );
}
