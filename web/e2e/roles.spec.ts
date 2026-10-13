import { expect, login, runFlow, test } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await login(page, "manager_a1");
});

test("Quản lý cửa hàng: bị khóa cửa hàng, vẫn bỏ được đề xuất của cửa hàng mình", async ({ page }) => {
  await expect(page.getByTestId("store-select")).toBeDisabled();
  const turn = await runFlow(page, 1);
  const card = turn.getByTestId("proposal-card").first();
  await card.getByTestId("proposal-reject").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã bỏ");
});

test("Quản lý cửa hàng hỏi về cửa hàng khác: API từ chối 403, UI hiện lý do tiếng Việt", async ({ page, failures }) => {
  failures.allow(/\/api\/agent\/chat$/, 403);
  await page.getByTestId("chat-input").fill("Còn nhiều rau ở CH3");
  await page.getByTestId("chat-send").click();
  const error = page.getByTestId("turn").last().getByTestId("turn-error");
  await expect(error).toBeVisible();
  await expect(error).toContainText(/cửa hàng/i);
  await expect(page.getByTestId("turn").last().getByTestId("agent-answer")).toHaveCount(0);
});
