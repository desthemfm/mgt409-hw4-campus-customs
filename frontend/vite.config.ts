import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The FastAPI backend (backend/main.py) runs on port 8000: `uvicorn main:app --reload --port 8000`.
// The dev server forwards /api and /media to it, so the browser only ever talks to one origin
// (no CORS setup needed, and the login cookie just works).
const BACKEND_URL = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': BACKEND_URL,
      '/media': BACKEND_URL,
    },
  },
})
