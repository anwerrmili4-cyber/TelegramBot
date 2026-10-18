import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/visual",
  fullyParallel: false,
  forbidOnly: true,
  reporter: "line",
  timeout: 60_000,
  workers: 2,
  use: {
    colorScheme: "dark",
    locale: "fr-FR",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: "disabled",
      maxDiffPixelRatio: 0.015,
    },
  },
  webServer: [
    {
      command: "npm run dev -- --host 127.0.0.1 --port 4174",
      url: "http://127.0.0.1:4174/admin",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm --prefix ../storefront run dev -- --host 127.0.0.1 --port 4175",
      url: "http://127.0.0.1:4175",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
