import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: process.env.TEST_URL || "http://localhost:5173",
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH,
      args: ["--no-sandbox"],
    },
  },
  workers: 1,
  webServer: process.env.CI
    ? {
        command: "npm run preview",
        url: "http://localhost:4173",
        reuseExistingServer: false,
      }
    : undefined,
});
