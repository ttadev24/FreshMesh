import { expect, login, test } from "./fixtures";

test.describe("Đăng nhập", () => {
  test("chưa đăng nhập thì bị chuyển về /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByTestId("login-submit")).toBeVisible();
  });

  test("đăng nhập hợp lệ mở không gian làm việc của chuỗi", async ({ page }) => {
    await login(page, "owner_a");
    await expect(page.getByTestId("simulated-badge")).toHaveText("SIMULATED");
    await expect(page.getByTestId("mode-badge")).toHaveText(/LLM|Kịch bản/);
    await expect(page.getByTestId("store-select")).toBeVisible();
    // Reload keeps the session (sessionStorage mirror).
    await page.reload();
    await expect(page.getByTestId("flow-1")).toBeVisible();
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("sai mật khẩu hiện lỗi tiếng Việt và ở lại trang đăng nhập", async ({ page, failures }) => {
    failures.allow(/\/api\/auth\/login$/, 401);
    await page.goto("/login");
    await page.getByTestId("login-username").fill("owner_a");
    await page.getByTestId("login-password").fill("sai-mat-khau");
    await page.getByTestId("login-submit").click();
    const error = page.getByTestId("login-error");
    await expect(error).toBeVisible();
    await expect(error).not.toBeEmpty();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("quản lý cửa hàng bị khóa vào cửa hàng của mình", async ({ page }) => {
    await login(page, "manager_a1");
    await expect(page.getByTestId("store-select")).toBeDisabled();
    await expect(page.getByTestId("user-role")).toContainText("Quản lý cửa hàng");
  });
});
