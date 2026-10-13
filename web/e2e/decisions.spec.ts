import { createPanelDraft, expect, login, NO_RAW_VALUES, runTool, showPane, test } from "./fixtures";

// Contract of 2026-10-13 (docs/api-contract-notes.md): markdown vs transfer is compared in cash only; the transfer's
// avoided-stockout value is reported separately; edits that leave figures un-recomputed carry a Vietnamese note;
// an approved markdown carries its execution record. Drafts are created from the tool panels via POST /api/drafts.

const NON_CASH = "giá trị tránh thiếu hàng, không phải tiền mặt";

test.beforeEach(async ({ page }) => {
  await login(page, "owner_a");
  // CH3: the demo store with surplus vegetables and a routed transfer to compare against.
  await page.getByTestId("store-select").selectOption("A-CH3");
});

test("Giảm giá hay điều chuyển: so sánh bằng tiền mặt, giá trị tránh thiếu hàng ghi riêng", async ({ page }) => {
  // The recommendation is whatever the cash comparison says for the current data: read it from the API reply.
  const reply = page.waitForResponse((r) => r.url().includes("/api/transfer/plan") && r.ok());
  await runTool(page, "stock");
  const { summary: cmp } = await (await reply).json();
  const summary = page.getByTestId("stock-summary");
  await expect(summary).toBeVisible();
  await expect(summary.locator("dl")).toContainText("tiền mặt");
  const best = cmp.markdown_gain_vnd >= cmp.transfer_gain_vnd ? "Giảm giá theo giờ" : "Điều chuyển";
  expect(cmp.recommended).toBe(cmp.markdown_gain_vnd >= cmp.transfer_gain_vnd ? "markdown" : "transfer");
  await expect(summary.locator('[data-best="true"]')).toContainText(best);

  // The non-cash value is its own line, outside the cash figures and outside the transfer's net.
  const nonCash = page.getByTestId("stock-noncash");
  await expect(nonCash).toContainText(NON_CASH);
  await expect(nonCash).toContainText("đ");
  await expect(summary.locator("dl")).not.toContainText(NON_CASH);
  await expect(page.getByTestId("transfer-net-cash")).toContainText("Lợi ròng tiền mặt");
  await expect(page.getByTestId("transfer-net-cash")).not.toContainText(NON_CASH);
  await expect(page.getByTestId("transfer-noncash")).toContainText(NON_CASH);
  await expect(page.getByTestId("stock-comparison")).not.toContainText(NO_RAW_VALUES);
});

test("Giảm giá: sửa lịch thì lợi ích chưa tính lại có ghi chú, duyệt hiện bản ghi thực thi", async ({ page }) => {
  await runTool(page, "stock");
  const card = await createPanelDraft(page, "stock", "draft-markdown");
  await expect(card).toHaveAttribute("data-kind", "apply_markdown");
  await expect(card.getByTestId("draft-cash-total")).toContainText("đ");

  await card.getByTestId("proposal-edit").click();
  // Cap the first item at "no discount": always a change while the schedule discounts anything.
  await card.getByTestId("proposal-cap-select").first().selectOption("0");
  await card.getByTestId("proposal-save").click();
  await expect(card.getByTestId("proposal-approve")).toBeVisible();
  await expect(card.getByTestId("draft-note")).toContainText("chưa tính lại");
  await expect(card.getByTestId("draft-cash-total")).toContainText("chưa tính lại");
  await expect(card).not.toContainText(NO_RAW_VALUES);

  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");
  const record = card.getByTestId("execution-record");
  await expect(record).toContainText("Lịch giảm giá đã duyệt");
  await expect(record.getByTestId("execution-item").first()).toBeVisible();
  await expect(record.getByTestId("execution-cash-total")).toContainText("chưa tính lại");
  await expect(record).not.toContainText(NO_RAW_VALUES);
});

test("Giảm giá: duyệt lịch đề xuất hiện tổng lợi thêm bằng tiền", async ({ page }) => {
  await runTool(page, "stock");
  const card = await createPanelDraft(page, "stock", "draft-markdown");
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");
  const record = card.getByTestId("execution-record");
  await expect(record.getByTestId("execution-item").first()).toContainText("đ");
  await expect(record.getByTestId("execution-cash-total")).toContainText(/\d đ/);
  await expect(record).not.toContainText(NO_RAW_VALUES);
});

test("Điều chuyển: phiếu điều chuyển từ bảng so sánh tách tiền mặt và giá trị tránh thiếu hàng", async ({ page }) => {
  await runTool(page, "stock");
  const card = await createPanelDraft(page, "stock", "draft-transfer");
  await expect(card).toHaveAttribute("data-kind", "create_transfer");
  await expect(card).toContainText("lợi ròng tiền mặt");
  await expect(card).not.toContainText(NO_RAW_VALUES);
  await card.getByTestId("proposal-reject").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã bỏ");
});

test("Đơn đặt hàng: số lượng tự sửa thì % hàng bỏ / hết hàng chưa tính lại có ghi chú", async ({ page }) => {
  await runTool(page, "inventory");
  const card = await createPanelDraft(page, "inventory", "draft-purchase");
  // The proposal card names the data behind its figures, like the panel it came from.
  await expect(card.getByTestId("draft-sources").getByTestId("source-ref").first()).toBeVisible();
  await card.getByTestId("proposal-edit").click();
  const qty = card.getByTestId("proposal-qty-input").first();
  const step = Number((await qty.getAttribute("step")) ?? "1");
  await qty.fill(String(Number(await qty.inputValue()) + step));
  await card.getByTestId("proposal-save").click();
  await expect(card.getByTestId("proposal-approve")).toBeVisible();
  await expect(card.getByTestId("draft-note")).toContainText("chưa tính lại");
  await expect(card).not.toContainText(NO_RAW_VALUES);
  await expect(card).not.toContainText("bỏ dự kiến");
});

test("Gửi lộ trình: bản nháp từ bản đồ lộ trình, duyệt thì chuyển trạng thái đã gửi", async ({ page }) => {
  await runTool(page, "route");
  const card = await createPanelDraft(page, "route", "draft-dispatch");
  await expect(card).toHaveAttribute("data-kind", "dispatch_routes");
  await expect(card).toContainText("km");
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã gửi");
});

test("Mô hình dự báo chưa sẵn sàng (503 model_not_ready): báo lỗi tiếng Việt trên bảng", async ({ page, failures }) => {
  failures.allow(/\/api\/inventory\/plan$/, 503);
  // Simulated failure: the live demo has trained models. No message_vi, so the UI's own Vietnamese text is used.
  await page.route(/\/api\/inventory\/plan$/, (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "model_not_ready" } }) }),
  );
  await showPane(page, "dashboard");
  await page.getByTestId("tool-inventory").click();
  const error = page.getByTestId("tool-error-inventory");
  await expect(error).toContainText("Mô hình dự báo");
  await expect(error).toContainText("chưa sẵn sàng");
  await expect(page.getByTestId("plan-table")).toHaveCount(0);
});
