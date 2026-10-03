import { useMemo, useState } from 'react';
import Grid from '@mui/material/Grid';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import ToggleButton from '@mui/material/ToggleButton';
import ShowChartIcon from '@mui/icons-material/esm/ShowChart';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import HoldingCard from '../components/HoldingCard.jsx';
import EtfComparisonTable from '../components/EtfComparisonTable.jsx';
import EtfComposition from '../components/EtfComposition.jsx';
import DonutChart from '../charts/DonutChart.jsx';
import { DeltaBarChart } from '../charts/HorizontalBarChart.jsx';
import MultiSeriesLineChart from '../charts/MultiSeriesLineChart.jsx';
import ComboValueChart from '../charts/ComboValueChart.jsx';
import { PALETTE } from '../format.js';

// Total gain % rewards whichever broker/manager happened to hold its
// positions longest, not which one actually performed best per year — the
// "average yearly" mode swaps in the blended XIRR instead, dropping groups
// too young to annualize meaningfully (same 90-day floor as individual
// holdings).
function performanceSeries(entries, nameKey, mode) {
  const rows = mode === 'annualized' ? entries.filter((e) => e.reliable && e.annualized_pct != null) : entries;
  return {
    labels: rows.map((e) => e[nameKey]),
    values: rows.map((e) => (mode === 'annualized' ? e.annualized_pct : e.gain_pct)),
  };
}

export default function Etf({ data }) {
  const [performanceMode, setPerformanceMode] = useState('total');
  const etfHoldings = useMemo(() => data.holdings.filter((h) => h.category === 'ETF'), [data.holdings]);

  const byBroker = useMemo(() => {
    const groups = new Map();
    for (const h of etfHoldings) {
      if (!groups.has(h.broker)) groups.set(h.broker, []);
      groups.get(h.broker).push(h);
    }
    return groups;
  }, [etfHoldings]);

  // The same fund can be held at more than one broker (e.g. VWCE on both
  // Degiro and MeDirect) — each broker's position is its own holding now,
  // so the ticker alone is ambiguous wherever holdings are labeled outside
  // their broker-grouped card. Disambiguate only where it's actually
  // needed, so the common case still reads as a plain ticker.
  const tickerCounts = useMemo(() => {
    const counts = new Map();
    for (const h of etfHoldings) counts.set(h.ticker, (counts.get(h.ticker) || 0) + 1);
    return counts;
  }, [etfHoldings]);
  const holdingLabel = (h) => (tickerCounts.get(h.ticker) > 1 ? `${h.ticker} (${h.broker})` : h.ticker);

  const brokerPerf = performanceSeries(data.etf_by_broker, 'broker', performanceMode);
  const managerPerf = performanceSeries(data.etf_by_manager, 'manager', performanceMode);

  return (
    <section id="etf">
      <SectionHeader
        icon={ShowChartIcon}
        title="ETF"
        hint="Broker/manager comparisons, holdings, and performance."
      />

      <Grid container spacing={3}>
        <ChartCard title="ETF value over time" wide>
          <ComboValueChart
            valueData={data.allocation_over_time}
            valueKey="ETF"
            purchasesMonthly={data.etf_purchases_monthly}
            color={PALETTE[0]}
          />
        </ChartCard>

        <ChartCard title="ETF value by broker">
          <DonutChart labels={data.etf_by_broker.map((b) => b.broker)} values={data.etf_by_broker.map((b) => b.current_value)} />
        </ChartCard>

        <ChartCard
          title="ETF performance by broker"
          hint={
            performanceMode === 'annualized'
              ? 'Average yearly gain (XIRR), blended across each broker\'s positions. Groups holding a position under 90 days are excluded — too little time for a meaningful annualized rate.'
              : "Total gain since purchase — a newer broker with recently opened positions will naturally read near 0%, and a broker held longer accumulates more total gain even at the same yearly rate."
          }
          headerAction={
            <ToggleButtonGroup
              value={performanceMode}
              exclusive
              onChange={(_, v) => v && setPerformanceMode(v)}
              size="small"
              sx={{ mb: 1.5 }}
            >
              <ToggleButton value="total">Total gain</ToggleButton>
              <ToggleButton value="annualized">Avg. yearly gain</ToggleButton>
            </ToggleButtonGroup>
          }
        >
          <DeltaBarChart labels={brokerPerf.labels} values={brokerPerf.values} />
        </ChartCard>

        <ChartCard
          title="ETF value by manager"
          hint="Manager is guessed from the fund name text (iShares/Vanguard/SPDR/...) — the sheet has no dedicated field for it."
        >
          <DonutChart labels={data.etf_by_manager.map((m) => m.manager)} values={data.etf_by_manager.map((m) => m.current_value)} />
        </ChartCard>

        <ChartCard
          title="ETF performance by manager"
          hint={
            performanceMode === 'annualized'
              ? 'Average yearly gain (XIRR), blended across each manager\'s positions. Same toggle as the broker chart above.'
              : undefined
          }
        >
          <DeltaBarChart labels={managerPerf.labels} values={managerPerf.values} />
        </ChartCard>

        <ChartCard
          title="Portfolio composition"
          wide
          hint="Blended from each fund's tracked index (MSCI World, S&P 500, ...), weighted by current value — approximate reference weights, not a live look-through of actual fund constituents. Per-company breakdown isn't available from the sheet."
        >
          <EtfComposition composition={data.etf_composition} />
        </ChartCard>

        <ChartCard title="Holdings" wide hint="Grouped by broker, one card per ISIN. Fully sold-out positions aren't shown.">
          <Stack spacing={3}>
            {Array.from(byBroker.entries()).map(([broker, group]) => (
              <div key={broker}>
                <Typography variant="overline" color="text.secondary">
                  {broker}
                </Typography>
                <Grid container spacing={2} sx={{ mt: 0.5 }}>
                  {group.map((h) => (
                    <Grid item xs={12} sm={6} lg={4} key={h.key}>
                      <HoldingCard h={h} />
                    </Grid>
                  ))}
                </Grid>
              </div>
            ))}
          </Stack>
        </ChartCard>

        <ChartCard
          title="Holding performance (annualized)"
          hint="Money-weighted annualized return (XIRR) — accounts for when each purchase happened, so a position built up over years isn't compared 1:1 against one bought last month. Positions held under 90 days are excluded (too little time for a meaningful annualized rate)."
        >
          <DeltaBarChart
            labels={etfHoldings.filter((h) => h.reliable && h.annualized_pct != null).map(holdingLabel)}
            values={etfHoldings.filter((h) => h.reliable && h.annualized_pct != null).map((h) => h.annualized_pct)}
          />
        </ChartCard>

        <ChartCard
          title="Holdings — capital invested over time"
          wide
          hint={
            'Cumulative "Money Spent EUR" per holding — the sheet\'s Total Net column re-prices every past lot ' +
            "at today's price, so a true value-over-time series isn't available; this tracks position size instead."
          }
        >
          <MultiSeriesLineChart
            data={data.holdings_cost_basis_over_time}
            seriesKeys={etfHoldings.map((h) => h.key)}
            seriesLabels={Object.fromEntries(etfHoldings.map((h) => [h.key, holdingLabel(h)]))}
            fill={false}
          />
        </ChartCard>

        <ChartCard
          title="ETF comparison"
          wide
          hint="All ETF holdings side by side. Hover an index name for what it actually tracks — index/benchmark and manager are guessed from the fund name text, not a dedicated field in the sheet."
        >
          <EtfComparisonTable holdings={data.holdings} />
        </ChartCard>
      </Grid>
    </section>
  );
}
