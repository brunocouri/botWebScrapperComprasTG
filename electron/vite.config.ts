import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  server: { host: 'localhost', port: 5173, strictPort: true },
  plugins: [react(), tailwindcss(), {
    name: 'comprastg-dev-csp',
    apply: 'serve',
    transformIndexHtml(html) {
      // React Refresh e estilos injetados existem somente em desenvolvimento.
      return html.replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
        .replace('ws://localhost:5173', 'ws://localhost:*')
    },
  }],
})
