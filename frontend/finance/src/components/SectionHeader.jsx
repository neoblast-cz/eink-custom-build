import Stack from '@mui/material/Stack';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

export default function SectionHeader({ icon: Icon, title, hint }) {
  return (
    <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2.5 }}>
      <Box
        sx={{
          width: 48,
          height: 48,
          flexShrink: 0,
          borderRadius: 2,
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon sx={{ fontSize: 28 }} />
      </Box>
      <Box>
        <Typography variant="h2">{title}</Typography>
        {hint && (
          <Typography variant="body2" color="text.secondary">
            {hint}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}
