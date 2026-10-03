import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import StatTile from './StatTile.jsx';
import { eur, pct } from '../format.js';

// Crowdlending/Savings stat row — current value, gross deposited/withdrawn
// (so an exited platform's near-total withdrawal is visible instead of
// looking like a loss), total interest earned (the real "gain" figure),
// and an XIRR-based annualized return.
export default function CashFlowStats({ stats }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2}>
        <StatTile label="Current value" value={eur(stats.current_value)} />
        <StatTile label="Total deposited" value={eur(stats.total_deposited)} />
        <StatTile label="Total withdrawn" value={eur(stats.total_withdrawn)} />
        <StatTile label="Total interest earned" value={eur(stats.total_interest)} delta="up" />
        {stats.annualized_pct != null && (
          <StatTile
            label="Annualized return"
            value={`${pct(stats.annualized_pct, 1)}/yr`}
            delta={stats.annualized_pct >= 0 ? 'up' : 'down'}
          />
        )}
      </Stack>
    </Paper>
  );
}
