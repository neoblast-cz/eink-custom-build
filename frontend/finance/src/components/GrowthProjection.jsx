import { useMemo, useState } from 'react';
import Box from '@mui/material/Box';
import Grid from '@mui/material/Grid';
import Stack from '@mui/material/Stack';
import Slider from '@mui/material/Slider';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import FormControlLabel from '@mui/material/FormControlLabel';
import Switch from '@mui/material/Switch';
import Alert from '@mui/material/Alert';
import LinearProgress from '@mui/material/LinearProgress';
import { Line } from 'react-chartjs-2';
import StatTile from './StatTile.jsx';
import { eur } from '../format.js';
import { lineOptions } from '../charts/common.js';

const FIRE_WITHDRAWAL_RATE = 0.04; // the "4%" in the 4% rule

function ageFromBirthDate(birthDateStr) {
  const birth = new Date(birthDateStr);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  const hadBirthdayThisYear =
    today.getMonth() > birth.getMonth() ||
    (today.getMonth() === birth.getMonth() && today.getDate() >= birth.getDate());
  if (!hadBirthdayThisYear) age -= 1;
  return age;
}

export default function GrowthProjection({ growthAssetValue, growthXirr }) {
  const [birthDate, setBirthDate] = useState('1987-02-01');
  const [years, setYears] = useState(10);
  const [applyTax, setApplyTax] = useState(false);
  const [taxRate, setTaxRate] = useState(10);
  const [taxExemption, setTaxExemption] = useState(10000);
  const [annualExpenses, setAnnualExpenses] = useState(30000);
  const [monthlySavings, setMonthlySavings] = useState(0);

  if (growthXirr === null) {
    return (
      <Typography variant="body2" color="text.secondary">
        Not enough purchase history to compute a reliable annualized rate yet.
      </Typography>
    );
  }

  const REALISTIC = growthXirr;
  const OPTIMISTIC = REALISTIC + 4;
  const PESSIMISTIC = Math.max(REALISTIC - 4, 1);
  const projectedValue = (rate, y) => growthAssetValue * Math.pow(1 + rate / 100, y);
  // Rough estimate of Belgium's capital gains tax on financial assets
  // (introduced 2026) applied to a single eventual sale: taxable gain =
  // projected value minus today's value minus the annual exemption, taxed
  // at a flat rate. Real rules are more involved (a grandfathered reference
  // value for pre-2026 holdings, possible exemption carry-over) — this
  // ignores all of that, so treat it as a ballpark, not tax advice.
  const afterTaxValue = (value) => {
    const gain = Math.max(0, value - growthAssetValue);
    const taxableGain = Math.max(0, gain - taxExemption);
    return value - taxableGain * (taxRate / 100);
  };
  const ageNow = ageFromBirthDate(birthDate);
  const targetYear = new Date().getFullYear() + years;

  // 4% rule: a portfolio of 25x annual expenses can sustain a 4%/yr
  // withdrawal indefinitely (historically, in the studies the rule comes
  // from) — so "FIRE number" = expenses x 25 = expenses / 4%. Based on the
  // same stale, no-further-contributions portfolio as the rest of this
  // tool, per your framing: how close does *just letting this sit* get you.
  const fireNumber = annualExpenses * (1 / FIRE_WITHDRAWAL_RATE);
  const fireProgressPct = fireNumber > 0 ? Math.min(100, (growthAssetValue / fireNumber) * 100) : 0;
  const alreadyFire = fireNumber > 0 && growthAssetValue >= fireNumber;
  // With monthly savings added on top of the stale portfolio, this solves
  // FV = P(1+i)^n + PMT*((1+i)^n - 1)/i for n (in months, i = monthly rate),
  // then converts back to years — the closed-form solution for a lump sum
  // plus a level monthly contribution compounding at the same rate.
  // monthlySavings=0 collapses back to the plain compound-growth case.
  const yearsToFire = (annualRatePct) => {
    if (!fireNumber || alreadyFire) return 0;
    if (annualRatePct <= 0) return Infinity;
    if (monthlySavings <= 0) {
      return Math.log(fireNumber / growthAssetValue) / Math.log(1 + annualRatePct / 100);
    }
    const i = Math.pow(1 + annualRatePct / 100, 1 / 12) - 1;
    const x = (fireNumber + monthlySavings / i) / (growthAssetValue + monthlySavings / i);
    if (x <= 0) return Infinity;
    return Math.log(x) / Math.log(1 + i) / 12;
  };
  const formatYearsToFire = (rate) => {
    const y = yearsToFire(rate);
    if (!Number.isFinite(y)) return 'not at this rate';
    if (y <= 0) return 'already there';
    const wholeYears = Math.ceil(y);
    return `${y.toFixed(1)} yrs (${new Date().getFullYear() + wholeYears}, age ${ageNow + wholeYears})`;
  };

  const chartData = useMemo(() => {
    const labels = Array.from({ length: years + 1 }, (_, y) => `${new Date().getFullYear() + y}`);
    const series = (rate) => labels.map((_, y) => projectedValue(rate, y));
    const datasets = [
      {
        label: `Pessimistic (${PESSIMISTIC.toFixed(1)}%/yr)`,
        data: series(PESSIMISTIC),
        borderColor: '#c62828',
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
        tension: 0.1,
      },
      {
        label: `Realistic (${REALISTIC.toFixed(1)}%/yr)`,
        data: series(REALISTIC),
        borderColor: '#2a78d6',
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
        tension: 0.1,
      },
      {
        label: `Optimistic (${OPTIMISTIC.toFixed(1)}%/yr)`,
        data: series(OPTIMISTIC),
        borderColor: '#1b8a5a',
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
        tension: 0.1,
      },
    ];
    if (fireNumber > 0) {
      datasets.push({
        label: `FIRE number (${eur(fireNumber)})`,
        data: labels.map(() => fireNumber),
        borderColor: '#6b7280',
        borderDash: [6, 4],
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
        tension: 0,
      });
    }
    return { labels, datasets };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [years, growthXirr, growthAssetValue, fireNumber]);

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Extrapolates your current ETF/Stock holdings ({eur(growthAssetValue)}) forward from their actual
        money-weighted annualized return ({REALISTIC.toFixed(2)}%/yr) — not your total net worth, since that
        also includes new money you add, cash/savings, and other asset classes. No further contributions
        assumed: this is &quot;if I stopped buying today and just held.&quot;
      </Typography>

      <Grid container spacing={3} alignItems="center" sx={{ mb: 3 }}>
        <Grid item xs={12} sm={4}>
          <TextField
            label="Your birth date"
            type="date"
            size="small"
            fullWidth
            value={birthDate}
            onChange={(e) => setBirthDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
          />
        </Grid>
        <Grid item xs={12} sm={8}>
          <Typography variant="caption" color="text.secondary">
            Years from now: {years}
          </Typography>
          <Slider min={1} max={40} value={years} onChange={(_, v) => setYears(v)} />
        </Grid>
      </Grid>

      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2} sx={{ mb: 3 }}>
        <StatTile label="Your age now" value={ageNow} />
        <StatTile label={`In ${years} years`} value={`${targetYear} · age ${ageNow + years}`} />
        <StatTile
          label={`Pessimistic (${PESSIMISTIC.toFixed(1)}%/yr)`}
          value={eur(projectedValue(PESSIMISTIC, years))}
          delta="down"
        />
        <StatTile label={`Realistic (${REALISTIC.toFixed(1)}%/yr)`} value={eur(projectedValue(REALISTIC, years))} />
        <StatTile
          label={`Optimistic (${OPTIMISTIC.toFixed(1)}%/yr)`}
          value={eur(projectedValue(OPTIMISTIC, years))}
          delta="up"
        />
      </Stack>

      <Box sx={{ height: 300, mb: 3 }}>
        <Line data={chartData} options={lineOptions({ legend: true })} />
      </Box>

      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        FIRE number (4% rule)
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        A portfolio of 25× your annual living expenses can (per the studies the rule comes from) sustain a 4%/yr
        withdrawal indefinitely.{' '}
        {monthlySavings > 0
          ? "\"Progress to FIRE\" is today's snapshot (stale portfolio, no savings yet), but the years-to-FIRE estimates below assume you keep contributing this monthly amount, compounding alongside the portfolio."
          : 'Measured against the same stale portfolio as above — no further contributions. Add a monthly savings amount below to factor ongoing contributions into the years-to-FIRE estimate.'}
      </Typography>

      <Grid container spacing={3} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={5}>
          <TextField
            label="Annual living expenses (€)"
            type="number"
            size="small"
            fullWidth
            value={annualExpenses}
            onChange={(e) => setAnnualExpenses(Number(e.target.value))}
          />
        </Grid>
        <Grid item xs={12} sm={5}>
          <TextField
            label="Monthly savings (€)"
            type="number"
            size="small"
            fullWidth
            value={monthlySavings}
            onChange={(e) => setMonthlySavings(Number(e.target.value))}
          />
        </Grid>
      </Grid>

      <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2} sx={{ mb: 1.5 }}>
        <StatTile label="FIRE number (25× expenses)" value={eur(fireNumber)} />
        <StatTile label="Safe withdrawal today (4%)" value={`${eur(growthAssetValue * FIRE_WITHDRAWAL_RATE)}/yr`} />
        <StatTile
          label="Progress to FIRE"
          value={`${fireProgressPct.toFixed(1)}%`}
          delta={alreadyFire ? 'up' : undefined}
        />
      </Stack>

      <LinearProgress
        variant="determinate"
        value={fireProgressPct}
        color={alreadyFire ? 'success' : 'primary'}
        sx={{ height: 8, borderRadius: 4, mb: 2.5 }}
      />

      {alreadyFire ? (
        <Alert severity="success" sx={{ mb: 3 }}>
          This portfolio alone already covers your FIRE number at a 4%/yr withdrawal.
        </Alert>
      ) : (
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2} sx={{ mb: 3 }}>
          <StatTile label={`Pessimistic (${PESSIMISTIC.toFixed(1)}%/yr)`} value={formatYearsToFire(PESSIMISTIC)} delta="down" />
          <StatTile label={`Realistic (${REALISTIC.toFixed(1)}%/yr)`} value={formatYearsToFire(REALISTIC)} />
          <StatTile label={`Optimistic (${OPTIMISTIC.toFixed(1)}%/yr)`} value={formatYearsToFire(OPTIMISTIC)} delta="up" />
        </Stack>
      )}

      <FormControlLabel
        control={<Switch checked={applyTax} onChange={(e) => setApplyTax(e.target.checked)} size="small" />}
        label="Apply Belgian capital gains tax estimate (introduced 2026)"
      />

      {applyTax && (
        <Box sx={{ mt: 1 }}>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Rough estimate only, not tax advice — a flat rate on the gain above an annual exemption, applied as if
            everything were sold in one go at the end of the period. It ignores real details like the grandfathered
            reference value for holdings owned before 2026 and any exemption carry-over. Adjust the rate/exemption
            below if the enacted figures differ from what's shown.
          </Alert>
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Tax rate (%)"
                type="number"
                size="small"
                fullWidth
                value={taxRate}
                onChange={(e) => setTaxRate(Number(e.target.value))}
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                label="Annual exemption (€)"
                type="number"
                size="small"
                fullWidth
                value={taxExemption}
                onChange={(e) => setTaxExemption(Number(e.target.value))}
              />
            </Grid>
          </Grid>
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap rowGap={2}>
            <StatTile
              label={`Pessimistic, after tax (${PESSIMISTIC.toFixed(1)}%/yr)`}
              value={eur(afterTaxValue(projectedValue(PESSIMISTIC, years)))}
              delta="down"
            />
            <StatTile
              label={`Realistic, after tax (${REALISTIC.toFixed(1)}%/yr)`}
              value={eur(afterTaxValue(projectedValue(REALISTIC, years)))}
            />
            <StatTile
              label={`Optimistic, after tax (${OPTIMISTIC.toFixed(1)}%/yr)`}
              value={eur(afterTaxValue(projectedValue(OPTIMISTIC, years)))}
              delta="up"
            />
          </Stack>
        </Box>
      )}
    </Box>
  );
}
