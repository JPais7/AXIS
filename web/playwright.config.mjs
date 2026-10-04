import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  testMatch: ['workspace.spec.mjs', 'structure.spec.mjs', 'pharmacology.spec.mjs', 'cellular.spec.mjs'],
  workers: 1,
  use: { baseURL: process.env.AXIS_WORKSPACE_URL || 'http://127.0.0.1:8765', viewport: { width: 1440, height: 1000 }, channel: process.env.AXIS_BROWSER_EXECUTABLE || process.env.AXIS_BROWSER_CHANNEL === 'chromium' ? undefined : process.env.AXIS_BROWSER_CHANNEL || 'msedge', launchOptions: process.env.AXIS_BROWSER_EXECUTABLE ? { executablePath: process.env.AXIS_BROWSER_EXECUTABLE } : {} },
  reporter: 'list'
});
