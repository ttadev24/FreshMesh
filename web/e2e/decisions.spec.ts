import { expect, login, runFlow, showPane, test } from "./fixtures";

// Contract of 2026-10-13 (docs/api-contract-notes.md): markdown vs transfer is compared in cash only; the transfer's
// avoided-stockout value is reported separately; edits that leave figures un-recomputed carry a Vietnamese note;
// an approved markdown carries its execution record.

const NON_CASH = "giá trị tránh thiếu hàng, không phải tiền mặt";
const NO_RAW_VALUES = /NaN|null|undefined/;

test.beforeEach(async ({ page }) => {
  await login(page, "owner_a");
  // Flow 2 at CH3: the demo store with surplus vegetables and a routed transfer to compare against.
  await page.getByTestId("store-select").selectOption("A-CH3");
});

test("Luồng 2: so sánh bằng tiền mặt, giá trị tránh thiếu hàng ghi riêng", async ({ page }) => {
  await runFlow(page, 2);
  await showPane(page, "dashboard");
  const summary = page.getByTestId("stock-summary");
  await expect(summary).toBeVisible();
  await expect(summary.locator("dl")).toContainText("tiền mặt");
  // CH3 now recommends the markdown on the cash basis.
  await expect(summary.locator('[data-best="true"]')).toContainText("Giảm giá theo giờ");

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
  const turn = await runFlow(page, 2);
  const card = turn.locator('[data-testid="proposal-card"][data-kind="apply_markdown"]').first();
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
  const turn = await runFlow(page, 2);
  const card = turn.locator('[data-testid="proposal-card"][data-kind="apply_markdown"]').first();
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");
  const record = card.getByTestId("execution-record");
  await expect(record.getByTestId("execution-item").first()).toContainText("đ");
  await expect(record.getByTestId("execution-cash-total")).toContainText(/\d đ/);
  await expect(record).not.toContainText(NO_RAW_VALUES);
});

test("Đơn đặt hàng: số lượng tự sửa thì % hàng bỏ / hết hàng chưa tính lại có ghi chú", async ({ page }) => {
  const turn = await runFlow(page, 1);
  const card = turn.getByTestId("proposal-card").first();
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

test("Mô hình dự báo chưa sẵn sàng (503 model_not_ready): báo lỗi tiếng Việt", async ({ page, failures }) => {
  failures.allow(/\/api\/agent\/scenario\/1$/, 503);
  // Simulated: the live demo has trained models. No message_vi, so the UI's own Vietnamese text is used.
  await page.route(/\/api\/agent\/scenario\/1$/, (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "model_not_ready" } }) }),
  );
  await showPane(page, "chat");
  await page.getByTestId("flow-1").click();
  const error = page.getByTestId("turn").last().getByTestId("turn-error");
  await expect(error).toContainText("Mô hình dự báo");
  await expect(error).toContainText("chưa sẵn sàng");
});
