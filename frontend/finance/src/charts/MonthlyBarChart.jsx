import { Bar } from 'react-chartjs-2';
import Box from '@mui/material/Box';
import { barOptions } from './common.js';
import { PALETTE } from '../format.js';

// Vertical bars, one per month — {month: 'YYYY-MM', amount} rows. Used for
// "interest per month" (not cumulative — isolates the recurring signal)
// and, via ComboValueChart, for monthly purchase amounts.
export default function MonthlyBarChart({ data, color = PALETTE[0], height = 220 }) {
  const chartData = {
    labels: data.map((e) => e.month),
    datasets: [{ data: data.map((e) => e.amount), backgroundColor: color }],
  };
  return (
    <Box sx={{ height }}>
      <Bar data={chartData} options={barOptions({ horizontal: false })} />
    </Box>
  );
}

// Same shape, but one series per key (e.g. institution), stacked — rows are
// {month: 'YYYY-MM', [key]: amount, ...}, with each key only present from
// whichever month it first appears.
export function StackedMonthlyBarChart({ data, seriesKeys, seriesLabels = {}, height = 260 }) {
  const chartData = {
    labels: data.map((e) => e.month),
    datasets: seriesKeys.map((key, i) => ({
      label: seriesLabels[key] || key,
      data: data.map((e) => e[key] || 0),
      backgroundColor: PALETTE[i % PALETTE.length],
    })),
  };
  return (
    <Box sx={{ height }}>
      <Bar data={chartData} options={barOptions({ horizontal: false, stacked: true, legend: true })} />
    </Box>
  );
}
