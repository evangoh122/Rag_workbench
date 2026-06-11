import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const plugins = [react(), tailwindcss()]

if (process.env.ANALYZE) {
  const { visualizer } = await import('rollup-plugin-visualizer')
  plugins.push(visualizer({
    open: false,
    filename: 'bundle-analysis.html',
    gzipSize: true,
    brotliSize: true,
  }))
}

// https://vite.dev/config/
export default defineConfig({
  plugins,
  envDir: '../',
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom')) {
            return 'react-vendor';
          }
          if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark') || id.includes('node_modules/unified') || id.includes('node_modules/mdast')) {
            return 'markdown';
          }
          if (id.includes('node_modules/@xyflow')) {
            return 'flow';
          }
          if (id.includes('node_modules/lucide-react')) {
            return 'icons';
          }
        },
      },
    },
  },
})
