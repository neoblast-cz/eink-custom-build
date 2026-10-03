import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  LineController,
  BarController,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import ChartDataLabels from 'chartjs-plugin-datalabels';

// LineController/BarController are needed explicitly (not just the
// Element types) for the generic <Chart> component used by mixed-type
// charts (ComboValueChart) — react-chartjs-2's typed <Line>/<Bar> wrappers
// self-register their own controller, but the generic one doesn't.
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  LineController,
  BarController,
  Title,
  Tooltip,
  Legend,
  Filler,
  ChartDataLabels,
);

// Registered globally (chartjs-plugin-datalabels has no clean per-chart-type
// opt-in), but off by default — only donutOptions() in charts/common.js
// turns it on, so line/bar charts aren't affected.
ChartJS.defaults.set('plugins.datalabels', { display: false });
