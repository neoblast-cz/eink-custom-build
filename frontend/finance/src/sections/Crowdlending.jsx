import Grid from '@mui/material/Grid';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import HandshakeIcon from '@mui/icons-material/esm/Handshake';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CashFlowStats from '../components/CashFlowStats.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';
import { StackedMonthlyBarChart } from '../charts/MonthlyBarChart.jsx';
import { HorizontalBarChart } from '../charts/HorizontalBarChart.jsx';

export default function Crowdlending({ data }) {
  const cumulative = data.crowdlending_position_by_place;
  const exited = new Set(data.crowdlending_exited_platforms);

  const placeKeys = cumulative.length
    ? Object.keys(cumulative[cumulative.length - 1]).filter((k) => k !== 'date')
    : [];
  const orderedPlaces = [...placeKeys].sort((a, b) => (a === 'Other' ? 1 : b === 'Other' ? -1 : 0));
  const seriesLabels = Object.fromEntries(
    orderedPlaces.map((p) => [p, exited.has(p) ? `${p} (exited)` : p]),
  );

  const interestPlaceKeys = data.interest_cumulative_by_place_crowdlending.length
    ? Object.keys(
        data.interest_cumulative_by_place_crowdlending[data.interest_cumulative_by_place_crowdlending.length - 1],
      ).filter((k) => k !== 'date')
    : [];
  const orderedInterestPlaces = [
    ...Object.keys(data.interest_by_place_crowdlending).filter(
      (k) => k !== 'Other' && interestPlaceKeys.includes(k),
    ),
    ...(interestPlaceKeys.includes('Other') ? ['Other'] : []),
  ];

  return (
    <section id="crowdlending">
      <SectionHeader
        icon={HandshakeIcon}
        title="Crowdlending"
        hint="P2P lending platforms — Mintos, PeerBerry, EstateGuru, and similar."
      />

      <CashFlowStats stats={data.crowdlending_stats} />

      {exited.size > 0 && (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 3 }}>
          <Typography variant="body2" color="text.secondary">
            Exited platforms:
          </Typography>
          {[...exited].sort().map((p) => (
            <Chip key={p} size="small" label={p} variant="outlined" />
          ))}
        </Stack>
      )}

      <Grid container spacing={3}>
        <ChartCard
          title="Cumulative portfolio by platform"
          wide
          hint="Reconstructed running balance per platform (deposits + bonuses + interest − withdrawals) — approximate, since a defaulted loan's principal loss isn't a recorded transaction. Exited platforms are labeled but may not settle exactly at zero for the same reason."
        >
          <MultiSeriesLineChart data={cumulative} seriesKeys={orderedPlaces} seriesLabels={seriesLabels} />
        </ChartCard>

        <ChartCard
          title="Interest per month"
          wide
          hint='Interest actually posted each month, not cumulative — stacked by institution, top 7 by total, rest folded into "Other".'
        >
          <StackedMonthlyBarChart data={data.interest_monthly_crowdlending} seriesKeys={orderedInterestPlaces} />
        </ChartCard>

        <ChartCard
          title="Cumulative interest income by institution"
          wide
          hint='Accumulated interest posted over time, grouped by account. Top 7 by total, rest folded into "Other".'
        >
          <MultiSeriesLineChart data={data.interest_cumulative_by_place_crowdlending} seriesKeys={orderedInterestPlaces} />
        </ChartCard>

        <ChartCard title="Interest income by account" wide>
          <HorizontalBarChart
            labels={Object.keys(data.interest_by_place_crowdlending)}
            values={Object.values(data.interest_by_place_crowdlending)}
          />
        </ChartCard>
      </Grid>
    </section>
  );
}
