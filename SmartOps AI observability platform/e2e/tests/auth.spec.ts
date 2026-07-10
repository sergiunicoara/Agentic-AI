import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test.beforeEach(async ({ page }) => {
    // Clear auth cookie before each test
    await page.context().clearCookies();
  });

  test("unauthenticated root redirects to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page renders with default credentials pre-filled", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator("input[type=email]")).toHaveValue("admin@smartops.local");
    await expect(page.locator("input[type=password]")).toHaveValue("smartops_dev");
  });

  test("successful login redirects to /dashboard", async ({ page }) => {
    await page.goto("/login");
    await page.locator("button[type=submit]").click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 10_000 });
  });

  test("wrong password shows error message", async ({ page }) => {
    await page.goto("/login");
    await page.fill("input[type=password]", "wrong-password");
    await page.locator("button[type=submit]").click();
    await expect(page.locator("text=Invalid credentials")).toBeVisible({ timeout: 5_000 });
  });

  test("authenticated user visiting /login is redirected to /dashboard", async ({ page }) => {
    // Login first
    await page.goto("/login");
    await page.locator("button[type=submit]").click();
    await page.waitForURL(/\/dashboard/);
    // Now visit /login again
    await page.goto("/login");
    await expect(page).toHaveURL(/\/dashboard/);
  });

  test("sign-out clears session and redirects to /login", async ({ page }) => {
    await page.goto("/login");
    await page.locator("button[type=submit]").click();
    await page.waitForURL(/\/dashboard/);
    await page.locator("text=Sign out").click();
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
  });
});
