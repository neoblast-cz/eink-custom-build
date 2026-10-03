import { useState } from 'react';
import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import Stack from '@mui/material/Stack';
import { saveSpreadsheetUrl } from '../api.js';

export default function ConnectScreen({ status, onSaved }) {
  const [url, setUrl] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveSpreadsheetUrl(url);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ maxWidth: 520, mx: 'auto', mt: 6 }}>
      <Card>
        <CardContent sx={{ p: 4 }}>
          <Typography variant="h2" gutterBottom>
            Connect your portfolio
          </Typography>

          {status.fetch_error ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              Couldn&apos;t fetch the sheet: {status.fetch_error}
              <br />
              Check the spreadsheet ID and that your Google account still has access to it.
            </Alert>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Connect your portfolio Google Sheet to see the dashboard.
            </Typography>
          )}

          <Stack spacing={2} sx={{ mb: 3 }}>
            <TextField
              label="Spreadsheet URL or ID"
              placeholder="https://docs.google.com/spreadsheets/d/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              fullWidth
              size="small"
            />
            <Typography variant="caption" color="text.secondary">
              Paste the sheet URL — it must have Date/Value columns like the Historic and Portfolio tabs this
              dashboard expects.
            </Typography>
            <Box>
              <Button variant="contained" onClick={handleSave} disabled={!url || saving}>
                Save
              </Button>
            </Box>
          </Stack>

          {!status.google_authorized ? (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Set Google OAuth credentials in <a href="/permissions">Permissions</a> first, then:
              </Typography>
              <Button variant="outlined" href="/oauth/google_sheets/start">
                Authorize with Google
              </Button>
            </>
          ) : (
            <Alert severity="success">Authorized with Google — waiting on a spreadsheet ID above.</Alert>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
