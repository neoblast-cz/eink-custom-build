import { eur } from '../format.js';

export const axisTextColor = '#5f6368';
export const gridColor = '#e6e8ee';

export function lineOptions({ stacked = false, legend = true } = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        ticks: { maxTicksLimit: 10, color: axisTextColor },
        grid: { color: gridColor },
      },
      y: {
        stacked,
        ticks: { callback: eur, color: axisTextColor },
        grid: { color: gridColor },
      },
    },
    plugins: {
      legend: { display: legend, position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } },
      tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${eur(ctx.parsed.y)}` } },
    },
  };
}

export function barOptions({ horizontal = true, formatter = eur, stacked = false, legend = false } = {}) {
  // The value axis (the one with numbers to format) is x for horizontal
  // bars, y for vertical — the category axis (labels: names, months, ...)
  // never gets the € formatter run over its tick text.
  const valueAxis = { stacked, ticks: { callback: formatter, color: axisTextColor }, grid: { color: gridColor } };
  const categoryAxis = { stacked, ticks: { color: axisTextColor }, grid: { display: false } };
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? 'y' : 'x',
    scales: horizontal ? { x: valueAxis, y: categoryAxis } : { x: categoryAxis, y: valueAxis },
    plugins: {
      legend: { display: legend, position: 'bottom', labels: { boxWidth: 12, usePointStyle: true, color: axisTextColor } },
      tooltip: {
        callbacks: stacked
          ? { label: (ctx) => `${ctx.dataset.label}: ${formatter(horizontal ? ctx.parsed.x : ctx.parsed.y)}` }
          : { label: (ctx) => formatter(horizontal ? ctx.parsed.x : ctx.parsed.y) },
      },
    },
  };
}

export function donutOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true, color: axisTextColor } },
      tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${eur(ctx.parsed)}` } },
      // Value + % printed directly on each slice — the legend still carries
      // identity, but the reader shouldn't have to hover to get the number.
      datalabels: {
        display: (ctx) => {
          const data = ctx.dataset.data;
          const total = data.reduce((a, b) => a + b, 0);
          return total > 0 && data[ctx.dataIndex] / total > 0.03; // hide slivers too thin to label
        },
        formatter: (value, ctx) => {
          const data = ctx.dataset.data;
          const total = data.reduce((a, b) => a + b, 0);
          const percent = total > 0 ? (value / total) * 100 : 0;
          return [eur(value), `${percent.toFixed(1)}%`];
        },
        color: '#fff',
        textStrokeColor: 'rgba(0,0,0,0.45)',
        textStrokeWidth: 3,
        font: { size: 11, weight: 600 },
        textAlign: 'center',
      },
    },
  };
}
