import { useState } from 'react';
import Button from '@mui/material/Button';
import CircularProgress from '@mui/material/CircularProgress';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import CameraAltIcon from '@mui/icons-material/esm/CameraAlt';
import { saveSnapshot } from '../api.js';

// Its own component (not state living in App) on purpose: App renders
// every section or every chart on the page, none of which memoize their
// Chart.js data/options objects, so a state change at the App level
// re-renders — and forces every chart to recompute — the entire page.
// Colocating this button's state here means a click only re-renders this
// button, not the other ~25 charts on the page.
export default function SnapshotButton() {
  const [state, setState] = useState({ saving: false, text: null, link: null, severity: 'success' });

  const handleClick = async () => {
    setState({ saving: true, text: null, link: null, severity: 'success' });
    try {
      const result = await saveSnapshot();
      if (result.screenshot_link) {
        setState({
          saving: false,
          text: `Snapshot saved to the "${result.sheet}" tab (${result.timestamp}).`,
          link: result.screenshot_link,
          severity: 'success',
        });
      } else {
        // Numbers row still saved — only the screenshot half failed — so
        // this is a partial success (warning), not a full error.
        setState({
          saving: false,
          text: `Numbers saved to "${result.sheet}" (${result.timestamp}), but the screenshot failed: ${result.screenshot_error}`,
          link: null,
          severity: 'warning',
        });
      }
    } catch (e) {
      setState({
        saving: false,
        text:
          e.code === 'insufficient_scope'
            ? 'Sheets is only authorized for read access — re-authorize in Permissions to allow snapshots.'
            : `Snapshot failed: ${e.message}`,
        link: null,
        severity: 'error',
      });
    }
  };

  return (
    <>
      <Button
        variant="outlined"
        color="primary"
        size="small"
        fullWidth
        onClick={handleClick}
        disabled={state.saving}
        startIcon={state.saving ? <CircularProgress size={16} /> : <CameraAltIcon />}
      >
        {state.saving ? 'Saving…' : 'Save snapshot'}
      </Button>

      <Snackbar
        open={Boolean(state.text)}
        autoHideDuration={10000}
        onClose={() => setState((s) => ({ ...s, text: null }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={state.severity}
          onClose={() => setState((s) => ({ ...s, text: null }))}
          sx={{ width: '100%' }}
        >
          {state.text}
          {state.link && (
            <>
              {' '}
              <a href={state.link} target="_blank" rel="noreferrer">
                View screenshot
              </a>
            </>
          )}
        </Alert>
      </Snackbar>
    </>
  );
}
