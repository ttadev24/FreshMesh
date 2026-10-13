import { expect, login, runFlow, showPane, test } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await login(page, "owner_a");
});

test("Luồng 1: dự báo, 3 phương án, duyệt tạo trạng thái bản nháp", async ({ page }) => {
  const turn = await runFlow(page, 1);

  // Answer follows the fixed five-section template.
  const answer = turn.getByTestId("agent-answer");
  for (const section of ["Đề xuất", "Vì sao", "Độ tin cậy", "Giả định", "Việc cần bạn duyệt"]) {
    await expect(answer.getByText(section, { exact: true })).toBeVisible();
  }
  await expect(turn.getByTestId("tool-step").first()).toBeVisible();

  // Dashboard: forecast band chart + 3 plans.
  await showPane(page, "dashboard");
  const chart = page.getByTestId("forecast-chart");
  await expect(chart).toBeVisible();
  await expect(chart.locator("canvas").first()).toBeVisible();
  await expect(chart.getByTestId("confidence-badge")).toHaveText(/Cao|Trung bình|Thấp/);
  const plans = page.getByTestId("plan-table");
  await expect(plans.locator("tbody > tr[data-plan]")).toHaveCount(3);
  for (const label of ["An toàn", "Cân bằng", "Tiết kiệm"]) await expect(plans.getByText(label).first()).toBeVisible();
  await expect(plans.locator("tbody > tr[data-plan]").first()).toContainText("đ");

  // Approve the purchase-order draft.
  await showPane(page, "chat");
  const card = turn.getByTestId("proposal-card").first();
  await expect(card.getByTestId("draft-status")).toHaveText("Bản nháp, chờ duyệt");
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");
  await expect(card.getByTestId("proposal-approve")).toHaveCount(0);
});

test("Luồng 2: so sánh giảm giá với điều chuyển bằng tiền", async ({ page }) => {
  const turn = await runFlow(page, 2);
  await expect(turn.getByTestId("agent-answer")).toContainText("Đề xuất");
  await showPane(page, "dashboard");
  const panel = page.getByTestId("stock-comparison");
  await expect(panel).toBeVisible();
  await expect(panel).toContainText("đ");
});

test("Luồng 3: bản đồ có đường đi của xe và tóm tắt lộ trình", async ({ page }) => {
  const turn = await runFlow(page, 3);
  await expect(turn.getByTestId("agent-answer")).toBeVisible();
  await showPane(page, "dashboard");
  const map = page.getByTestId("route-map");
  await expect(map).toBeVisible();
  await expect(map.locator(".leaflet-container")).toBeVisible();
  // Vehicle polylines are SVG paths in Leaflet's overlay pane.
  const paths = map.locator(".leaflet-overlay-pane path.leaflet-interactive");
  await expect.poll(async () => paths.count()).toBeGreaterThan(0);
  await expect(page.getByTestId("vehicle-route").first()).toBeVisible();
  await expect(page.getByTestId("route-summary")).toContainText("km");
});

test("Chat: câu hỏi tự do được stream thành các bước rồi trả lời theo khuôn", async ({ page }) => {
  await page.getByTestId("chat-input").fill("Nhập rau và thịt cho mai thế nào?");
  await page.getByTestId("chat-send").click();
  const turn = page.getByTestId("turn").last();
  await expect(turn.getByTestId("step-list")).toBeVisible();
  await expect(turn.getByTestId("agent-answer")).toBeVisible({ timeout: 120_000 });
  await expect(turn.getByTestId("tool-step").first()).toBeVisible();
  await expect(turn.getByTestId("agent-answer").getByText("Việc cần bạn duyệt", { exact: true })).toBeVisible();
});
