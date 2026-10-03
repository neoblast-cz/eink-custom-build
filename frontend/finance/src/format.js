export const eur = (v) => `€${Math.round(v).toLocaleString()}`;

export const pct = (v, digits = 2) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`;

// Unit counts, up to 4 decimals, thousands-comma'd. NOT a manual trailing-
// zero strip: JS's default Number->String is already minimal (660 stays
// "660", 4.9171 stays "4.9171") — a regex trailing-zero strip on top of
// that (leftover from the old Python `'{:,.4f}'.format(x).rstrip('0')`
// port, where Python's format DOES pad with zeros) ate real digits, e.g.
// turning "660" into "66".
export const units = (v) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 });

// Validated 8-hue categorical order (light-mode steps) — fixed order, never
// reassigned by rank, so a series keeps its color if the list is filtered.
export const PALETTE = [
  '#2a78d6', '#eb6834', '#1baf7a', '#eda100',
  '#e87ba4', '#008300', '#4a3aa7', '#e34948',
];
