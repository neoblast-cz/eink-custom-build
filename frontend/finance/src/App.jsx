import { useEffect, useState, useCallback } from 'react';
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Stack from '@mui/material/Stack';
import Button from '@mui/material/Button';
import Drawer from '@mui/material/Drawer';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
// Import icons from the /esm/ subpath, not the package root (e.g. NOT
// `@mui/icons-material/Dashboard`). The root path resolves to the package's
// plain CJS build, and this project's Rolldown-based Vite build mis-interops
// its `React.memo(...)` export — the icon silently becomes a plain object
// and React throws "Element type is invalid" at render time. The /esm/ file
// is real ESM and bundles correctly.
import DashboardIcon from '@mui/icons-material/esm/Dashboard';
import ShowChartIcon from '@mui/icons-material/esm/ShowChart';
import BusinessCenterIcon from '@mui/icons-material/esm/BusinessCenter';
import HandshakeIcon from '@mui/icons-material/esm/Handshake';
import SavingsIcon from '@mui/icons-material/esm/Savings';
import PaymentsIcon from '@mui/icons-material/esm/Payments';
import MonetizationOnIcon from '@mui/icons-material/esm/MonetizationOn';
import CurrencyBitcoinIcon from '@mui/icons-material/esm/CurrencyBitcoin';
import LocalFireDepartmentIcon from '@mui/icons-material/esm/LocalFireDepartment';

import { fetchDashboardData } from './api.js';
import useScrollSpy from './hooks/useScrollSpy.js';
import ConnectScreen from './components/ConnectScreen.jsx';
import SnapshotButton from './components/SnapshotButton.jsx';
import Overview from './sections/Overview.jsx';
import Etf from './sections/Etf.jsx';
import Stocks from './sections/Stocks.jsx';
import Crowdlending from './sections/Crowdlending.jsx';
import Savings from './sections/Savings.jsx';
import Cash from './sections/Cash.jsx';
import Crypto from './sections/Crypto.jsx';
import GrowthProjectionSection from './sections/GrowthProjectionSection.jsx';
import SimpleCategorySection from './sections/SimpleCategorySection.jsx';

const DRAWER_WIDTH = 220;

const NAV_SECTIONS = [
  { id: 'overview', label: 'Overview', icon: DashboardIcon },
  { id: 'etf', label: 'ETF', icon: ShowChartIcon },
  { id: 'stocks', label: 'Stocks', icon: BusinessCenterIcon },
  { id: 'crowdlending', label: 'Crowdlending', icon: HandshakeIcon },
  { id: 'savings', label: 'Savings', icon: SavingsIcon },
  { id: 'cash', label: 'Cash', icon: PaymentsIcon },
  { id: 'gold', label: 'Gold', icon: MonetizationOnIcon },
  { id: 'crypto', label: 'Crypto', icon: CurrencyBitcoinIcon },
  { id: 'growth-projection', label: 'Growth Projection', icon: LocalFireDepartmentIcon },
];

const APP_NAV = [
  { label: 'Dashboard', href: '/' },
  { label: 'Photos', href: '/photos' },
  { label: 'Analytics', href: '/analytics' },
  { label: 'Finance', href: '/finance' },
  { label: 'Settings', href: '/settings' },
  { label: 'Permissions', href: '/permissions' },
];

export default function App() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchDashboardData()
      .then(setStatus)
      .catch((e) => setStatus({ has_data: false, fetch_error: e.message }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeSection = useScrollSpy(
    status?.has_data ? NAV_SECTIONS.map((s) => s.id) : [],
  );

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ mr: 4, fontWeight: 700 }}>
            EinkPi
          </Typography>
          <Stack direction="row" spacing={1} sx={{ flexGrow: 1 }}>
            {APP_NAV.map((item) => (
              <Button
                key={item.href}
                href={item.href}
                color={item.href === '/finance' ? 'primary' : 'inherit'}
                variant={item.href === '/finance' ? 'outlined' : 'text'}
                size="small"
              >
                {item.label}
              </Button>
            ))}
          </Stack>
        </Toolbar>
      </AppBar>

      {status?.has_data && (
        <Drawer
          variant="permanent"
          sx={{
            width: DRAWER_WIDTH,
            flexShrink: 0,
            [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: 'border-box' },
          }}
        >
          <Toolbar />
          <List>
            {NAV_SECTIONS.map(({ id, label, icon: Icon }) => (
              <ListItemButton key={id} selected={activeSection === id} onClick={() => scrollToSection(id)}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <Icon fontSize="small" />
                </ListItemIcon>
                <ListItemText primary={label} primaryTypographyProps={{ fontSize: 14 }} />
              </ListItemButton>
            ))}
          </List>
          <Divider sx={{ mx: 2 }} />
          <Box sx={{ p: 2 }}>
            <SnapshotButton />
          </Box>
        </Drawer>
      )}

      <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default', minHeight: '100vh' }}>
        <Toolbar />
        <Container maxWidth="xl" sx={{ py: 4 }}>
          <Typography variant="h1" sx={{ mb: 0.5, fontSize: '1.8rem' }}>
            Finance
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>
            Local-only dashboard over your portfolio Google Sheet, fetched live. Not part of the e-ink display or
            the Pi deploy.
          </Typography>

          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}>
              <CircularProgress />
            </Box>
          )}

          {!loading && status && !status.has_data && <ConnectScreen status={status} onSaved={load} />}

          {!loading && status?.has_data && (
            <Stack spacing={6}>
              <Overview data={status} />
              <Etf data={status} />
              <Stocks data={status} />
              <Crowdlending data={status} />
              <Savings data={status} />
              <Cash data={status} />
              <SimpleCategorySection
                id="gold"
                icon={MonetizationOnIcon}
                title="Gold"
                hint="Physical or paper gold holdings."
                category="Gold"
                data={status}
              />
              <Crypto data={status} />
              <GrowthProjectionSection data={status} />
            </Stack>
          )}
        </Container>
      </Box>
    </Box>
  );
}
