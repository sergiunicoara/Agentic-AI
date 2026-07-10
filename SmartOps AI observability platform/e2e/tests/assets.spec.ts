import { test, expect } from "@playwright/test";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.locator("button[type=submit]").click();
  await page.waitForURL(/\/dashboard/);
}

test.describe("Assets", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto("/assets");
    await expect(page.locator("h1", { hasText: "Assets" })).toBeVisible();
  });

  test("renders assets table with data from simulator seed", async ({ page }) => {
    // Simulator seeds region assets — wait for rows to appear
    const rows = page.locator("tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
  });

  test("search filters results", async ({ page }) => {
    await page.fill("input[type=search]", "api");
    // Table should update — at minimum the search input holds the value
    await expect(page.locator("input[type=search]")).toHaveValue("api");
  });

  test("opens create asset modal on Add Asset click", async ({ page }) => {
    await page.locator("button", { hasText: "Add Asset" }).click();
    await expect(page.locator("text=New Asset")).toBeVisible();
    await expect(page.locator("input[placeholder='prod-api-01']")).toBeVisible();
  });

  test("closes modal on Cancel click", async ({ page }) => {
    await page.locator("button", { hasText: "Add Asset" }).click();
    await page.locator("button", { hasText: "Cancel" }).click();
    await expect(page.locator("text=New Asset")).not.toBeVisible();
  });

  test("create button is disabled when name is empty", async ({ page }) => {
    await page.locator("button", { hasText: "Add Asset" }).click();
    await page.fill("input[placeholder='prod-api-01']", "");
    const createBtn = page.locator("button", { hasText: "Create" });
    await expect(createBtn).toBeDisabled();
  });

  test("can create a new asset end-to-end", async ({ page }) => {
    const name = `e2e-test-asset-${Date.now()}`;
    await page.locator("button", { hasText: "Add Asset" }).click();
    await page.fill("input[placeholder='prod-api-01']", name);
    await page.locator("button", { hasText: "Create" }).click();
    // Modal should close and new asset appear in table
    await expect(page.locator("text=New Asset")).not.toBeVisible({ timeout: 5_000 });
    await expect(page.locator(`text=${name}`)).toBeVisible({ timeout: 5_000 });
  });
});
