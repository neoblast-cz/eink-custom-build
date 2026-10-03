import { useMemo, useState } from 'react';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { eur, pct, units } from '../format.js';

// `value` reflects what's actually shown, not necessarily the raw field —
// e.g. annualized_pct sorts as unknown (always last) for a "too new" or
// price-unavailable row, matching the "too new"/"n/a" text in that cell,
// rather than silently sorting by a number the user can't see.
const COLUMNS = [
  { id: 'ticker', label: 'Ticker', align: 'left', value: (h) => h.ticker },
  { id: 'name', label: 'Name', align: 'left', value: (h) => h.name },
  { id: 'index', label: 'Index / benchmark', align: 'left', value: (h) => h.index },
  { id: 'manager', label: 'Manager', align: 'left', value: (h) => h.manager },
  { id: 'hedge', label: 'Hedge', align: 'left', value: (h) => h.hedge || 'Unhedged' },
  { id: 'broker', label: 'Broker', align: 'left', value: (h) => h.broker },
  { id: 'units', label: 'Units', align: 'right', value: (h) => h.units },
  { id: 'current_value', label: 'Value', align: 'right', value: (h) => h.current_value },
  { id: 'gain_pct', label: 'Gain', align: 'right', value: (h) => (h.price_unavailable ? null : h.gain_pct) },
  {
    id: 'annualized_pct',
    label: 'Annualized',
    align: 'right',
    value: (h) => (!h.price_unavailable && h.reliable && h.annualized_pct != null ? h.annualized_pct : null),
  },
];

function compareBy(a, b, getValue) {
  const av = getValue(a);
  const bv = getValue(b);
  // Unknown values (null) always sort last regardless of direction — an
  // absent number isn't "low," it just isn't there to compare.
  if (av == null && bv == null) return 0;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === 'string') return av.localeCompare(bv);
  return av - bv;
}

export default function EtfComparisonTable({ holdings }) {
  const [orderBy, setOrderBy] = useState('current_value');
  const [order, setOrder] = useState('desc');

  const etfs = useMemo(() => {
    const col = COLUMNS.find((c) => c.id === orderBy);
    const sorted = [...holdings.filter((h) => h.category === 'ETF')].sort((a, b) => compareBy(a, b, col.value));
    return order === 'desc' ? sorted.reverse() : sorted;
  }, [holdings, orderBy, order]);

  const handleSort = (id) => {
    if (orderBy === id) {
      setOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setOrderBy(id);
      setOrder('desc');
    }
  };

  // Every position here happens to be an accumulating ETF, so a
  // "Distribution" column would just repeat the same value down every row —
  // no differentiation, no reason to spend a column on it. (Still shown per
  // holding on its card, in case that ever stops being uniformly true.)
  return (
    <TableContainer sx={{ overflowX: 'auto' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableCell key={col.id} align={col.align} sortDirection={orderBy === col.id ? order : false}>
                <TableSortLabel
                  active={orderBy === col.id}
                  direction={orderBy === col.id ? order : 'asc'}
                  onClick={() => handleSort(col.id)}
                >
                  {col.label}
                </TableSortLabel>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {etfs.map((h) => (
            <TableRow key={h.key} hover>
              <TableCell>{h.ticker}</TableCell>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{h.name}</TableCell>
              <TableCell>
                {h.index_description ? (
                  <Tooltip title={h.index_description} arrow>
                    <Typography
                      variant="body2"
                      component="span"
                      sx={{ textDecoration: 'underline dotted', cursor: 'help' }}
                    >
                      {h.index}
                    </Typography>
                  </Tooltip>
                ) : (
                  h.index
                )}
              </TableCell>
              <TableCell>{h.manager}</TableCell>
              <TableCell>{h.hedge || 'Unhedged'}</TableCell>
              <TableCell>{h.broker}</TableCell>
              <TableCell align="right">{units(h.units)}</TableCell>
              <TableCell align="right">
                {h.price_unavailable ? (
                  <Tooltip title="Sheet's live price lookup errored for this ticker — showing cost basis instead." arrow>
                    <Typography
                      variant="body2"
                      component="span"
                      sx={{ textDecoration: 'underline dotted', cursor: 'help' }}
                    >
                      {eur(h.current_value)}*
                    </Typography>
                  </Tooltip>
                ) : (
                  eur(h.current_value)
                )}
              </TableCell>
              <TableCell
                align="right"
                sx={{ color: h.price_unavailable ? 'text.secondary' : h.gain >= 0 ? 'success.main' : 'error.main' }}
              >
                {h.price_unavailable ? 'n/a' : pct(h.gain_pct)}
              </TableCell>
              <TableCell
                align="right"
                sx={{
                  color:
                    h.price_unavailable || h.annualized_pct == null
                      ? 'text.primary'
                      : h.annualized_pct >= 0 ? 'success.main' : 'error.main',
                }}
              >
                {h.price_unavailable
                  ? 'n/a'
                  : h.reliable && h.annualized_pct != null
                    ? `${pct(h.annualized_pct)}/yr`
                    : 'too new'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
