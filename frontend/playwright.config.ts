import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:3009",
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: "node --experimental-strip-types tests/fake-api.ts",
      port: 8109,
    },
    {
      command: "npm run dev -- --webpack --hostname 127.0.0.1 --port 3009",
      port: 3009,
      env: {
        API_INTERNAL_URL: "http://127.0.0.1:8109",
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8109",
      },
    },
  ],
});
