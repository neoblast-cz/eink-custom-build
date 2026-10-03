import { Bar } from 'react-chartjs-2';
import Box from '@mui/material/Box';
import { barOptions } from './common.js';
import { PALETTE, pct } from '../format.js';

export function HorizontalBarChart({ labels, values, color = PALETTE[2], height = 260 }) {
  const data = { labels, datasets: [{ data: values, backgroundColor: color }] };
  return (
    <Box sx={{ height }}>
      <Bar data={data} options={barOptions({ horizontal: true })} />
    </Box>
  );
}

// Same shape, but each bar is colored by sign (gain vs loss) — used for
// broker/manager/holding *performance* charts, i.e. always a %, never a €
// amount — the story is "which of these lost money," not a magnitude
// comparison.
export function DeltaBarChart({ labels, values, height = 260 }) {
  const colors = values.map((v) => (v >= 0 ? '#1b8a5a' : '#c62828'));
  const data = { labels, datasets: [{ data: values, backgroundColor: colors }] };
  return (
    <Box sx={{ height }}>
      <Bar data={data} options={barOptions({ horizontal: true, formatter: (v) => pct(v, 1) })} />
    </Box>
  );
}
