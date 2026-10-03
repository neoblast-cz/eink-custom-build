import Box from '@mui/material/Box';
import { Chart } from 'react-chartjs-2';
import { eur } from '../format.js';
import { axisTextColor, gridColor } from './common.js';

const toEpoch = (dateStr) => new Date(dateStr).getTime();

// Value-over-time line with purchase months marked as thin bars sharing the
// same timeline and the same y-axis — not a dual-axis chart: the bars are
// deliberately drawn at a small fixed height (a rug-plot marker, "a
// purchase happened here"), not scaled to the purchase amount, which would
// need its own axis to stay legible next to a much larger cumulative value.
// The real € amount is still available on hover.
export default function ComboValueChart({ valueData, valueKey, purchasesMonthly, color, height = 300 }) {
  const linePoints = valueData.map((e) => ({ x: toEpoch(e.date), y: e[valueKey] || 0 }));
  const maxValue = Math.max(1, ...linePoints.map((p) => p.y));
  const markerHeight = maxValue * 0.05;

  const barPoints = purchasesMonthly.map((e) => ({ x: toEpoch(`${e.month}-15`), y: markerHeight }));

  const data = {
    datasets: [
      {
        type: 'line',
        label: valueKey,
        data: linePoints,
        borderColor: color,
        backgroundColor: color + '22',
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.1,
        order: 2,
      },
      {
        type: 'bar',
        label: 'Purchase',
        data: barPoints,
        backgroundColor: color,
        barThickness: 4,
        order: 1,
        // Custom fields (not a standard Chart.js dataset property) — read
        // back in the tooltip callback below to show the real € amount,
        // since the bar's drawn height is a fixed marker, not the value.
        purchaseAmounts: purchasesMonthly.map((e) => e.amount),
        purchaseMonths: purchasesMonthly.map((e) => e.month),
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        type: 'linear',
        ticks: {
          color: axisTextColor,
          maxTicksLimit: 10,
          callback: (v) => new Date(v).toLocaleDateString(undefined, { year: 'numeric', month: 'short' }),
        },
        grid: { color: gridColor },
      },
      y: {
        ticks: { callback: eur, color: axisTextColor },
        grid: { color: gridColor },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => new Date(items[0].parsed.x).toLocaleDateString(),
          label: (ctx) => {
            if (ctx.dataset.type === 'bar') {
              const i = ctx.dataIndex;
              return `Purchased ${eur(ctx.dataset.purchaseAmounts[i])} (${ctx.dataset.purchaseMonths[i]})`;
            }
            return `${ctx.dataset.label}: ${eur(ctx.parsed.y)}`;
          },
        },
      },
    },
  };

  return (
    <Box sx={{ height }}>
      <Chart type="bar" data={data} options={options} />
    </Box>
  );
}
