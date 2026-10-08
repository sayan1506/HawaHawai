import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [react(), VitePWA({
    registerType: 'prompt',
    manifest: {
      name: 'HawaHawai — School Air-Safety Advisor', short_name: 'HawaHawai',
      description: 'A school air-safety advisor for Delhi-NCR.',
      theme_color: '#155e55', background_color: '#f4f8f5', display: 'standalone',
      start_url: '/', icons: [{src: '/icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any'}],
    },
    // Cache the app shell only. Health and future safety APIs must always use the network.
    workbox: {globPatterns: ['**/*.{js,css,html,svg}'], runtimeCaching: []},
  })],
});
