import { createTheme } from '@mui/material/styles';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: { main: '#3454d1' },
    success: { main: '#1b8a5a' },
    error: { main: '#c62828' },
    background: { default: '#f5f6fa', paper: '#ffffff' },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Segoe UI", Roboto, -apple-system, BlinkMacSystemFont, sans-serif',
    h1: { fontSize: '2.5rem', fontWeight: 700 },
    h2: { fontSize: '1.4rem', fontWeight: 600 },
    h3: { fontSize: '1.1rem', fontWeight: 600 },
  },
  components: {
    MuiCard: {
      defaultProps: { variant: 'outlined' },
      styleOverrides: { root: { borderRadius: 12 } },
    },
    MuiAppBar: {
      defaultProps: { color: 'inherit', elevation: 0 },
    },
  },
});

export default theme;
