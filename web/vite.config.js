import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const isWslMountedDrive = Boolean(process.env.WSL_DISTRO_NAME) && __dirname.startsWith('/mnt/')

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss()
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    // WSL + /mnt/* often misses filesystem events, which breaks Vite HMR.
    watch: isWslMountedDrive
      ? {
          usePolling: true,
          interval: 100
        }
      : undefined
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.spec.js', 'tests/unit/**/*.spec.js'],
    exclude: ['**/node_modules/**', '**/tests/e2e/**']
  }
})
