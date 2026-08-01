import { test, expect } from "@playwright/test";

const API = process.env.API_BASE_URL ?? "http://localhost:3000";

test.describe("API security contract", () => {
  test("protected telemetry routes reject anonymous requests", async ({ request }) => {
    const response = await request.get(`${API}/api/v1/metrics/instant?q=up`);
    expect(response.status()).toBe(401);
  });

  test("health endpoint emits baseline security headers", async ({ request }) => {
    const response = await request.get(`${API}/health`);
    expect(response.ok()).toBeTruthy();
    expect(response.headers()["x-content-type-options"]).toBe("nosniff");
    expect(response.headers()["x-frame-options"]).toBeTruthy();
  });
});
