import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import {apiBaseUrl} from './src/config.ts';

export default defineConfig(({mode, command}) => {
  if (command === 'build') apiBaseUrl(loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL, true);
  return {
  plugins: [react(), VitePWA({
    registerType: 'prompt',
    injectRegister: false,
    includeAssets: ['icon.svg', 'icon-192.png', 'icon-512.png'],
    manifest: {
      name: 'HawaHawai — School Air-Safety Advisor', short_name: 'HawaHawai',
      description: 'A school air-safety advisor for Delhi-NCR.',
      id: '/', lang: 'en', scope: '/',
      theme_color: '#155e55', background_color: '#f5f7f8', display: 'standalone',
      start_url: '/', icons: [
        {src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any'},
        {src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any'},
        {src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable'},
      ],
    },
    // Cache the app shell only. Health and future safety APIs must always use the network.
    workbox: {
      globPatterns: ['**/*.{js,css,html,svg,png,webmanifest}'],
      navigateFallbackDenylist: [/^\/v1\//, /^\/health/],
      // Explicit network-only policy, including cross-origin safety APIs.
      runtimeCaching: [{urlPattern: ({url}) => url.pathname.startsWith('/v1/') || url.pathname === '/health', handler: 'NetworkOnly'}],
    },
  })],
  };
});
