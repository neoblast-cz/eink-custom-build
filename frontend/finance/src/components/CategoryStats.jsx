import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import StatTile from './StatTile.jsx';
import { eur, pct } from '../format.js';

// Current value / contributed / gain for one or more categories, sourced
// from currentAllocation + contributionsByCategory. Categories without a
// "Money Spent EUR" trail in the sheet (e.g. Cash, Savings deposits) only
// show current value — there's no contribution figure to compare against.
export default function CategoryStats({ categories, currentAllocation, contributionsByCategory }) {
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2}>
        {categories.map((cat) => {
          const current = currentAllocation[cat] || 0;
          const contributed = contributionsByCategory[cat];
          const gain = contributed ? current - contributed : null;
          const gainPct = contributed ? (gain / contributed) * 100 : null;
          return (
            <Stack direction="row" spacing={4} key={cat}>
              <StatTile label={`${cat} — current value`} value={eur(current)} />
              {contributed != null && (
                <>
                  <StatTile label={`${cat} — contributed`} value={eur(contributed)} />
                  <StatTile
                    label={`${cat} — gain`}
                    value={`${gain >= 0 ? '+' : ''}${eur(gain)} (${pct(gainPct, 1)})`}
                    delta={gain >= 0 ? 'up' : 'down'}
                  />
                </>
              )}
            </Stack>
          );
        })}
      </Stack>
    </Paper>
  );
}
