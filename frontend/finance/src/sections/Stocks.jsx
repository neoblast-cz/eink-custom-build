import Grid from '@mui/material/Grid';
import Typography from '@mui/material/Typography';
import BusinessCenterIcon from '@mui/icons-material/esm/BusinessCenter';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CategoryStats from '../components/CategoryStats.jsx';
import HoldingCard from '../components/HoldingCard.jsx';
import ComboValueChart from '../charts/ComboValueChart.jsx';
import { PALETTE } from '../format.js';

export default function Stocks({ data }) {
  const stockHoldings = data.holdings.filter((h) => h.category === 'Stocks');

  return (
    <section id="stocks">
      <SectionHeader
        icon={BusinessCenterIcon}
        title="Stocks"
        hint="Individual company shares, kept separate from pooled ETF funds."
      />

      <CategoryStats
        categories={['Stocks']}
        currentAllocation={data.current_allocation}
        contributionsByCategory={data.contributions_by_category}
      />

      <Grid container spacing={3}>
        <ChartCard title="Stocks value over time" wide>
          <ComboValueChart
            valueData={data.allocation_over_time}
            valueKey="Stocks"
            purchasesMonthly={data.stock_purchases_monthly}
            color={PALETTE[0]}
          />
        </ChartCard>

        {stockHoldings.length ? (
          <ChartCard title="Holdings" wide hint="Individual stock rows carry no ISIN in the sheet — grouped by ticker instead, parsed from the purchase note (e.g. NASDAQ:META).">
            <Grid container spacing={2}>
              {stockHoldings.map((h) => (
                <Grid item xs={12} sm={6} lg={4} key={h.key}>
                  <HoldingCard h={h} />
                </Grid>
              ))}
            </Grid>
          </ChartCard>
        ) : (
          <Grid item xs={12}>
            <Typography variant="body2" color="text.secondary">
              No individual stock positions found — only the aggregate value and contribution above.
            </Typography>
          </Grid>
        )}
      </Grid>
    </section>
  );
}
