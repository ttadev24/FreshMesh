import { defineConfig, devices } from "@playwright/test";

// E2E against the real stack: FastAPI gateway (repo root, port 8100) + Next production server (3100).
// Flow 3 also needs the routing solver container (FRESHMESH_SOLVER_URL, see docker-compose.yml).
const WEB_PORT = 3100;
const API_PORT = 8100;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  // Scenarios write drafts/audit rows into the shared demo DB and call the solver: run serially.
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        deviceScaleFactor: 3,
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      command: `uv run uvicorn api.main:app --port ${API_PORT}`,
      cwd: "..",
      url: `http://localhost:${API_PORT}/api/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      // The gateway fails closed without a token-signing secret; the demo stack opts into the dev secret.
      env: { FRESHMESH_ALLOW_DEV_SECRET: "1" },
      stdout: "ignore",
      stderr: "pipe",
    },
    {
      command: `npm run build && npm run start`,
      url: `http://localhost:${WEB_PORT}/login`,
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
      env: { FRESHMESH_API_URL: `http://localhost:${API_PORT}` },
    },
  ],
});
