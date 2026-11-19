import { defineConfig,devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser", fullyParallel: false, workers: 1, timeout: 60000,
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3001", trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: process.platform === "win32" ? "chrome" : undefined } }],
  webServer: process.env.PLAYWRIGHT_BASE_URL ? undefined : { command: "node node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 3001", url: "http://127.0.0.1:3001", reuseExistingServer: false, timeout: 120000,
    env: { NEXT_PUBLIC_SUPABASE_URL: "https://poc.supabase.co", NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "test-publishable-key", NEXT_TELEMETRY_DISABLED: "1", NEXT_TEST_DIST_DIR: ".next-browser-tests" } },
});
