import Grid from '@mui/material/Grid';
import CurrencyBitcoinIcon from '@mui/icons-material/esm/CurrencyBitcoin';
import SectionHeader from '../components/SectionHeader.jsx';
import ChartCard from '../components/ChartCard.jsx';
import CategoryStats from '../components/CategoryStats.jsx';
import ComboValueChart from '../charts/ComboValueChart.jsx';
import { PALETTE } from '../format.js';

export default function Crypto({ data }) {
  return (
    <section id="crypto">
      <SectionHeader icon={CurrencyBitcoinIcon} title="Crypto" hint="Cryptocurrency holdings." />

      <CategoryStats
        categories={['Crypto']}
        currentAllocation={data.current_allocation}
        contributionsByCategory={data.contributions_by_category}
      />

      <Grid container spacing={3}>
        <ChartCard title="Crypto value over time" wide>
          <ComboValueChart
            valueData={data.allocation_over_time}
            valueKey="Crypto"
            purchasesMonthly={data.crypto_purchases_monthly}
            color={PALETTE[6]}
          />
        </ChartCard>
      </Grid>
    </section>
  );
}
