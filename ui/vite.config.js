import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Backend port is configurable (VITE_API_PORT in ui/.env, see ui/.env.example)
// instead of hardcoded, since the FastAPI backend's port has already drifted
// twice between docs/defaults (8000 legacy default, 8010 in the Zen Studio
// setup instructions) and whatever happens to be free on a given machine.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPort = env.VITE_API_PORT || '8010'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: `http://127.0.0.1:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
