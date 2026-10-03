import Grid from '@mui/material/Grid';
import SavingsIcon from '@mui/icons-material/esm/Savings';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CashFlowStats from '../components/CashFlowStats.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';
import { StackedMonthlyBarChart } from '../charts/MonthlyBarChart.jsx';
import { HorizontalBarChart } from '../charts/HorizontalBarChart.jsx';

export default function Savings({ data }) {
  const placeKeys = data.interest_cumulative_by_place_savings.length
    ? Object.keys(data.interest_cumulative_by_place_savings[data.interest_cumulative_by_place_savings.length - 1]).filter(
        (k) => k !== 'date',
      )
    : [];
  const orderedPlaces = [
    ...Object.keys(data.interest_by_place_savings).filter((k) => k !== 'Other' && placeKeys.includes(k)),
    ...(placeKeys.includes('Other') ? ['Other'] : []),
  ];

  return (
    <section id="savings">
      <SectionHeader icon={SavingsIcon} title="Savings" hint="Savings and term accounts held at banks." />

      <CashFlowStats stats={data.savings_stats} />

      <Grid container spacing={3}>
        <ChartCard
          title="Interest per month"
          wide
          hint='Interest actually posted each month, not cumulative — stacked by institution, top 7 by total, rest folded into "Other".'
        >
          <StackedMonthlyBarChart data={data.interest_monthly_savings} seriesKeys={orderedPlaces} />
        </ChartCard>

        <ChartCard
          title="Cumulative interest income by institution"
          wide
          hint='Accumulated interest posted over time, grouped by account. Top 7 by total, rest folded into "Other".'
        >
          <MultiSeriesLineChart data={data.interest_cumulative_by_place_savings} seriesKeys={orderedPlaces} />
        </ChartCard>

        <ChartCard title="Interest income by account" wide>
          <HorizontalBarChart
            labels={Object.keys(data.interest_by_place_savings)}
            values={Object.values(data.interest_by_place_savings)}
          />
        </ChartCard>
      </Grid>
    </section>
  );
}
