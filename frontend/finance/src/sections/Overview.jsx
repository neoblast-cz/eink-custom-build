import { useState } from 'react';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import DashboardIcon from '@mui/icons-material/esm/Dashboard';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import StatTile from '../components/StatTile.jsx';
import NetWorthChart from '../charts/NetWorthChart.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';
import DonutChart from '../charts/DonutChart.jsx';
import { eur, pct } from '../format.js';
import { ASSET_CATEGORIES } from '../constants.js';

export default function Overview({ data }) {
  const [showProjection, setShowProjection] = useState(false);
  const stats = data.net_worth_stats;

  return (
    <section id="overview">
      <SectionHeader
        icon={DashboardIcon}
        title="Overview"
        hint="Net worth, allocation, and where new capital is going."
      />

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Stack direction="row" spacing={5} alignItems="flex-end" flexWrap="wrap" useFlexGap rowGap={2}>
          <div>
            <Typography variant="caption" color="text.secondary" display="block">
              Net worth
            </Typography>
            <Typography variant="h1">{eur(stats.latest.value)}</Typography>
          </div>
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            {[
              ['vs_30d', '30 days'],
              ['vs_1y', '1 year'],
              ['vs_all_time', 'all time'],
            ].map(([key, label]) => {
              const d = stats[key];
              return (
                <StatTile
                  key={key}
                  label={`vs ${label}`}
                  value={`${d.change >= 0 ? '+' : ''}${eur(d.change)} (${pct(d.pct)})`}
                  delta={d.change >= 0 ? 'up' : 'down'}
                />
              );
            })}
          </Stack>
        </Stack>
      </Paper>

      <Grid container spacing={3}>
        <ChartCard title="Net worth over time" wide>
          <NetWorthChart
            netWorth={data.net_worth}
            showProjection={showProjection}
            onToggleProjection={setShowProjection}
          />
        </ChartCard>

        <ChartCard title="Asset allocation over time" wide>
          <MultiSeriesLineChart data={data.allocation_over_time} seriesKeys={ASSET_CATEGORIES} stacked />
        </ChartCard>

        <ChartCard title="Current allocation">
          <DonutChart
            labels={Object.keys(data.current_allocation)}
            values={Object.values(data.current_allocation)}
          />
        </ChartCard>

        <ChartCard title="Contributions by category">
          <DonutChart
            labels={Object.keys(data.contributions_by_category)}
            values={Object.values(data.contributions_by_category)}
          />
        </ChartCard>
      </Grid>
    </section>
  );
}
