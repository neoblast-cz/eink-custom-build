import Grid from '@mui/material/Grid';
import PaymentsIcon from '@mui/icons-material/esm/Payments';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CategoryStats from '../components/CategoryStats.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';
import DonutChart from '../charts/DonutChart.jsx';

export default function Cash({ data }) {
  return (
    <section id="cash">
      <SectionHeader
        icon={PaymentsIcon}
        title="Cash"
        hint="Money held on current/checking accounts, outside interest-bearing products."
      />

      <CategoryStats
        categories={['Cash']}
        currentAllocation={data.current_allocation}
        contributionsByCategory={data.contributions_by_category}
      />

      <Grid container spacing={3}>
        <ChartCard title="Cash value over time" wide>
          <MultiSeriesLineChart data={data.allocation_over_time} seriesKeys={['Cash']} legend={false} />
        </ChartCard>

        <ChartCard title="Cash by bank" wide>
          <DonutChart labels={Object.keys(data.cash_by_place)} values={Object.values(data.cash_by_place)} />
        </ChartCard>
      </Grid>
    </section>
  );
}
