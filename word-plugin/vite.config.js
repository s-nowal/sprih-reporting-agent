import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'
import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'
import json5Plugin from 'vite-plugin-json5'

// HTTPS is required for sideloading into Word — Office hosts refuse to load
// add-ins from non-HTTPS origins. WebView2 also refuses self-signed certs
// (no "Continue anyway" prompt), so for desktop sideload you need a cert
// signed by a CA that Windows trusts.
//
// Run once on Windows (PowerShell):
//   npx -y office-addin-dev-certs install
// then point HTTPS_CERT_FILE / HTTPS_KEY_FILE in .env.development.local at:
//   HTTPS_CERT_FILE=/mnt/c/Users/<you>/.office-addin-dev-certs/localhost.crt
//   HTTPS_KEY_FILE=/mnt/c/Users/<you>/.office-addin-dev-certs/localhost.key
//
// If those env vars aren't set, fall back to @vitejs/plugin-basic-ssl —
// fine for plain-browser testing but Word's WebView2 will refuse it.
function loadDevCert(env) {
  const certFile = env.HTTPS_CERT_FILE
  const keyFile = env.HTTPS_KEY_FILE
  if (certFile && keyFile && existsSync(certFile) && existsSync(keyFile)) {
    return {
      cert: readFileSync(certFile),
      key: readFileSync(keyFile),
    }
  }
  return null
}

// To avoid mixed-content blocks (HTTPS plugin → HTTP backend) and CORS
// preflights, the dev server reverse-proxies all backend paths to the
// FastAPI on :8000. The plugin's BASE_URL stays empty so fetches are
// same-origin relative paths that Vite forwards.
const BACKEND_PATHS = [
  '/threads',
  '/runs',
  '/assistants',
  '/sources',
  '/artifacts',
  '/info',
  '/health',
  '/google_auth',
]

const proxy = Object.fromEntries(
  BACKEND_PATHS.map((p) => [
    p,
    {
      target: 'http://localhost:8000',
      changeOrigin: true,
      // SSE responses must not be buffered by the proxy.
      configure: (proxyServer) => {
        proxyServer.on('proxyRes', (proxyRes) => {
          proxyRes.headers['x-accel-buffering'] = 'no'
        })
      },
    },
  ]),
)

export default defineConfig(({ mode }) => {
  // Load every var (no prefix filter) so non-VITE_ keys like
  // HTTPS_CERT_FILE come through into vite.config.js.
  const env = loadEnv(mode, process.cwd(), '')
  const trustedCert = loadDevCert(env)

  return {
    plugins: [
      tailwindcss(),
      ...(trustedCert ? [] : [basicSsl()]),
      vue(),
      json5Plugin(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      https: trustedCert ?? true,
      proxy,
    },
  }
})
