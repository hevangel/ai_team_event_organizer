import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// Dev server proxies /api and /mcp to the FastAPI backend.
//
// VITE_API_TARGET overrides the backend the dev server proxies to. The
// deployment box already runs something on 8000, so the dev stack uses 8002
// by default; set VITE_API_TARGET=http://127.0.0.1:8000 for the classic setup.
const apiTarget = process.env.VITE_API_TARGET || 'http://127.0.0.1:8002'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Vite 8 rejects Host headers it doesn't know about; the dev page is
    // opened by hostname on the deployment box, not just localhost.
    allowedHosts: ['localhost', '127.0.0.1', 'atlvpciedv01'],
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      '/mcp': { target: apiTarget, changeOrigin: true },
    },
  },
})
