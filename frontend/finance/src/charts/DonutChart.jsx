import { Pie } from 'react-chartjs-2';
import Box from '@mui/material/Box';
import { donutOptions } from './common.js';
import { PALETTE } from '../format.js';

export default function DonutChart({ labels, values, height = 260 }) {
  const data = {
    labels,
    datasets: [{ data: values, backgroundColor: PALETTE.slice(0, labels.length) }],
  };
  return (
    <Box sx={{ height }}>
      <Pie data={data} options={donutOptions()} />
    </Box>
  );
}
