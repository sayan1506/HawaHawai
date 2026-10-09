import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './e2e', workers: 1, retries: 0, forbidOnly: true,
  timeout: 45000, outputDir: '../.local/phase5-browser-results',
  reporter: [['list'], ['json', {outputFile: '../.local/phase5-browser-tests.json'}]],
  use: {browserName: 'chromium', channel: 'chrome', headless: true, viewport: {width: 1280, height: 900},
    baseURL: 'http://127.0.0.1:4173', screenshot: 'only-on-failure'},
  webServer: {command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true, timeout: 30000},
});
