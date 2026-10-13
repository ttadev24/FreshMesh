import { expect, login, runFlow, showPane, test } from "./fixtures";

test("Các tab: lịch sử quyết định, mạng lưới FL, giả định dữ liệu", async ({ page }) => {
  await login(page, "owner_a");
  const turn = await runFlow(page, 1);
  await turn.getByTestId("proposal-card").first().getByTestId("proposal-approve").click();
  await expect(turn.getByTestId("proposal-card").first().getByTestId("draft-status")).toHaveText("Đã duyệt");

  await showPane(page, "dashboard");
  await page.getByTestId("tab-audit").click();
  const audit = page.getByTestId("audit-list");
  await expect(audit).toBeVisible();
  await expect(audit.locator("li").first()).toBeVisible();

  await page.getByTestId("tab-fl").click();
  // The FL experiments have been run (docs/experiments), so the real panel must render, never the empty state.
  const fl = page.getByTestId("fl-panel");
  await expect(fl).toBeVisible();
  await expect(page.getByTestId("fl-not-ready")).toHaveCount(0);
  await expect(fl).toContainText("Chuỗi tham gia");
  await expect(fl).toContainText("dự báo đang dùng mô hình cục bộ");

  await page.getByTestId("tab-assumptions").click();
  const assumptions = page.getByTestId("assumptions-panel");
  await expect(assumptions).toBeVisible();
  await expect(assumptions).toContainText("SIMULATED");
  await expect(assumptions.locator("section").first()).toBeVisible();

  // Keyboard: arrow keys move between tabs.
  await page.getByTestId("tab-assumptions").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("tab-fl")).toHaveAttribute("aria-selected", "true");
});
