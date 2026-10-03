import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';

export default function ChartCard({ title, hint, wide, children, headerAction }) {
  return (
    <Grid item xs={12} md={wide ? 12 : 6}>
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Typography variant="h3" gutterBottom>
            {title}
          </Typography>
          {headerAction}
          {children}
          {hint && (
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1.5 }}>
              {hint}
            </Typography>
          )}
        </CardContent>
      </Card>
    </Grid>
  );
}
