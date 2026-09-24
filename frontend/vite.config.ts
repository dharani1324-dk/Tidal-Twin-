import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // CesiumJS ships a large (~4.8 MB) runtime that is lazy-loaded ONLY on the
    // /globe route (route-level dynamic import). It never touches the entry
    // bundle, so the default 500 kB warning is a false positive for it.
    chunkSizeWarningLimit: 6000,
  },
})
