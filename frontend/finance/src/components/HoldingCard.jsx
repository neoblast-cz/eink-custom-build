import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Chip from '@mui/material/Chip';
import ExpandMoreIcon from '@mui/icons-material/esm/ExpandMore';
import { eur, pct, units } from '../format.js';

function Row({ label, value }) {
  return (
    <Stack direction="row" justifyContent="space-between" sx={{ py: 0.4 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Stack>
  );
}

export default function HoldingCard({ h }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="subtitle1" fontWeight={600}>
          {h.name}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {h.isin ? `${h.ticker} · ${h.isin}` : h.ticker}
        </Typography>
        <Typography variant="h2" sx={{ mt: 1, mb: 1 }}>
          {eur(h.current_value)}
        </Typography>

        {h.price_unavailable && (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label="Price unavailable — showing cost basis"
            title="The sheet's live price lookup for this ticker is returning an error, so current value/gain can't be computed yet. Value shown is cost basis, not a live price."
            sx={{ mb: 1 }}
          />
        )}

        <Row label="Units held" value={units(h.units)} />
        <Row label="Cost basis" value={eur(h.cost_basis)} />
        <Stack direction="row" justifyContent="space-between" sx={{ py: 0.4 }}>
          <Typography variant="body2" color="text.secondary">
            Gain (total)
          </Typography>
          {h.price_unavailable ? (
            <Typography variant="body2" color="text.secondary">
              unavailable
            </Typography>
          ) : (
            <Typography variant="body2" color={h.gain >= 0 ? 'success.main' : 'error.main'} fontWeight={600}>
              {h.gain >= 0 ? '+' : ''}
              {eur(h.gain)} ({pct(h.gain_pct)})
            </Typography>
          )}
        </Stack>
        <Stack direction="row" justifyContent="space-between" sx={{ py: 0.4 }}>
          <Typography variant="body2" color="text.secondary">
            Annualized
          </Typography>
          {h.price_unavailable ? (
            <Typography variant="body2" color="text.secondary">
              unavailable
            </Typography>
          ) : h.reliable && h.annualized_pct !== null ? (
            <Typography
              variant="body2"
              color={h.annualized_pct >= 0 ? 'success.main' : 'error.main'}
              fontWeight={600}
            >
              {pct(h.annualized_pct)}/yr
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              held {h.held_days}d — too new
            </Typography>
          )}
        </Stack>

        {h.transactions?.length > 0 && (
          <Accordion disableGutters elevation={0} sx={{ mt: 1.5, '&:before': { display: 'none' } }}>
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ px: 0 }}>
              <Typography variant="caption" color="text.secondary">
                {h.transactions.length} transaction{h.transactions.length !== 1 ? 's' : ''}
              </Typography>
            </AccordionSummary>
            <AccordionDetails sx={{ px: 0 }}>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1.5 }}>
                {h.category === 'ETF' && (
                  <>
                    <Chip size="small" label={`Manager: ${h.manager}`} />
                    <Chip size="small" label={`Index: ${h.index}`} title={h.index_description || ''} />
                    <Chip size="small" label={`Distribution: ${h.distribution || '—'}`} />
                    <Chip size="small" label={`Hedge: ${h.hedge || 'Unhedged'}`} />
                  </>
                )}
                {h.units ? (
                  <Chip size="small" label={`Avg cost/unit: €${(h.cost_basis / h.units).toFixed(2)}`} />
                ) : null}
              </Stack>
              <TableContainer sx={{ maxWidth: '100%', overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell align="right">Units</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">Spent</TableCell>
                      <TableCell align="right">Value</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {h.transactions.map((t, i) => (
                      <TableRow key={i}>
                        <TableCell>{t.date}</TableCell>
                        <TableCell>{t.type}</TableCell>
                        <TableCell align="right">{t.units != null ? units(t.units) : '—'}</TableCell>
                        <TableCell align="right">{t.price != null ? eur(t.price) : '—'}</TableCell>
                        <TableCell align="right">{t.spent != null ? eur(t.spent) : '—'}</TableCell>
                        <TableCell align="right">{t.value != null ? eur(t.value) : '—'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </AccordionDetails>
          </Accordion>
        )}
      </CardContent>
    </Card>
  );
}
