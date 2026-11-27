import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173/common-cause/",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --base /common-cause/",
    url: "http://127.0.0.1:4173/common-cause/",
  },
});
