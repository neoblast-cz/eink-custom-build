import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built output is served by Flask as static files (no Node at runtime on
// the Pi or in prod) — fixed, unhashed filenames so the Flask template can
// reference them directly without parsing a manifest.
export default defineConfig({
  plugins: [react()],
  base: '/static/finance/',
  server: {
    // `npm run dev` proxies API calls to the Flask app so the page can be
    // developed standalone without a full production build each time.
    proxy: {
      '/finance/api': 'http://localhost:8080',
      '/oauth': 'http://localhost:8080',
      '/permissions': 'http://localhost:8080',
    },
  },
  build: {
    outDir: '../../static/finance',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'index.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: (info) =>
          info.name && info.name.endsWith('.css') ? 'index.css' : 'assets/[name][extname]',
      },
    },
  },
})
