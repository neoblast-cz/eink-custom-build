import Grid from '@mui/material/Grid';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CategoryStats from '../components/CategoryStats.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';

// Cash / Gold / Crypto all share the same shape: stat tiles + one
// value-over-time chart pulled straight from the allocation-over-time
// series the Overview section already plots, just isolated to one key.
export default function SimpleCategorySection({ id, icon, title, hint, category, data }) {
  return (
    <section id={id}>
      <SectionHeader icon={icon} title={title} hint={hint} />

      <CategoryStats
        categories={[category]}
        currentAllocation={data.current_allocation}
        contributionsByCategory={data.contributions_by_category}
      />

      <Grid container spacing={3}>
        <ChartCard title={`${category} value over time`} wide>
          <MultiSeriesLineChart data={data.allocation_over_time} seriesKeys={[category]} legend={false} />
        </ChartCard>
      </Grid>
    </section>
  );
}
