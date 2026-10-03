import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

export default function StatTile({ label, value, delta }) {
  const color = delta === 'up' ? 'success.main' : delta === 'down' ? 'error.main' : 'text.primary';
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="subtitle1" fontWeight={600} color={color}>
        {value}
      </Typography>
    </Box>
  );
}
