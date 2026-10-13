import { expect, login, runFlow, test } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await login(page, "owner_a");
});

test("Sửa số lượng rồi mới duyệt", async ({ page }) => {
  const turn = await runFlow(page, 1);
  const card = turn.getByTestId("proposal-card").first();
  await card.getByTestId("proposal-edit").click();
  const qty = card.getByTestId("proposal-qty-input").first();
  await expect(qty).toBeVisible();
  const original = Number(await qty.inputValue());
  // Purchase quantities must stay multiples of the supplier MOQ (the input's step).
  const step = Number((await qty.getAttribute("step")) ?? "1");
  await qty.fill(String(original + step));
  await card.getByTestId("proposal-save").click();
  // Saved: back to read mode, still a draft, new quantity shown.
  await expect(card.getByTestId("proposal-approve")).toBeVisible();
  await expect(card.getByTestId("draft-status")).toHaveText("Bản nháp, chờ duyệt");
  await expect(card.locator("table")).toContainText(new Intl.NumberFormat("vi-VN").format(original + step));
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");
});

test("Bỏ đề xuất", async ({ page }) => {
  const turn = await runFlow(page, 1);
  const card = turn.getByTestId("proposal-card").first();
  await card.getByTestId("proposal-reject").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã bỏ");
  await expect(card.getByTestId("proposal-approve")).toHaveCount(0);
});
