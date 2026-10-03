import { useState } from 'react';
import Box from '@mui/material/Box';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import ToggleButton from '@mui/material/ToggleButton';
import Typography from '@mui/material/Typography';
import DonutChart from '../charts/DonutChart.jsx';

// Blended region/sector breakdown across held ETFs — built from each
// fund's tracked index reference weights (finance_data.py), not a live
// look-through, since the sheet has no per-company or per-region field for
// any holding. A proportional chart (not a literal area-over-time chart)
// because there's no historical snapshot of "what an index was made of on
// date X" to plot against — only today's blend.
export default function EtfComposition({ composition }) {
  const [mode, setMode] = useState('region');
  const data = mode === 'region' ? composition.by_region : composition.by_sector;

  return (
    <Box>
      <ToggleButtonGroup value={mode} exclusive onChange={(_, v) => v && setMode(v)} size="small" sx={{ mb: 2 }}>
        <ToggleButton value="region">By region</ToggleButton>
        <ToggleButton value="sector">By industry</ToggleButton>
      </ToggleButtonGroup>
      {data.length ? (
        <DonutChart labels={data.map((d) => d.label)} values={data.map((d) => d.value)} height={360} />
      ) : (
        <Typography variant="body2" color="text.secondary">
          No composition data available for the indexes currently held.
        </Typography>
      )}
    </Box>
  );
}
