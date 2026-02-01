import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.spec.js', 'tests/unit/**/*.spec.js'],
    exclude: ['**/node_modules/**', '**/tests/e2e/**']
  }
})
