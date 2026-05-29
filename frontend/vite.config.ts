import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

function isAbsoluteUrl(value: string | undefined) {
  return Boolean(value && /^https?:\/\//i.test(value))
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = isAbsoluteUrl(env.VITE_API_PROXY_TARGET)
    ? env.VITE_API_PROXY_TARGET
    : isAbsoluteUrl(env.VITE_API_BASE_URL)
      ? env.VITE_API_BASE_URL
      : 'http://127.0.0.1:8765'

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
