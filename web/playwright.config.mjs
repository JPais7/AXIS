import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  testMatch: ['workspace.spec.mjs', 'structure.spec.mjs'],
  workers: 1,
  use: { baseURL: process.env.AXIS_WORKSPACE_URL || 'http://127.0.0.1:8765', viewport: { width: 1440, height: 1000 }, channel: process.env.AXIS_BROWSER_CHANNEL || 'msedge' },
  reporter: 'list'
});
