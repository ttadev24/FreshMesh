import { createPanelDraft, DEMO_PASSWORD, expect, HAS_LLM, login, NEEDS_LLM, runTool, showPane, test } from "./fixtures";

test.describe("Quản lý cửa hàng", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, "manager_a1");
  });

  test("bị khóa cửa hàng, vẫn tính và bỏ được đề xuất của cửa hàng mình", async ({ page }) => {
    await expect(page.getByTestId("store-select")).toBeDisabled();
    await runTool(page, "inventory");
    const card = await createPanelDraft(page, "inventory", "draft-purchase");
    await card.getByTestId("proposal-reject").click();
    await expect(card.getByTestId("draft-status")).toHaveText("Đã bỏ");
  });

  test("hỏi trợ lý về cửa hàng khác: bị từ chối, lý do tiếng Việt", async ({ page, failures }) => {
    test.skip(!HAS_LLM, NEEDS_LLM);
    failures.allow(/\/api\/agent\/chat$/, 403);
    await showPane(page, "chat");
    await page.getByTestId("chat-input").fill("Còn nhiều rau ở CH3, nên giảm giá hay điều chuyển?");
    await page.getByTestId("chat-send").click();
    const turn = page.getByTestId("turn").last();
    // Either the gateway refuses the request (403) or the agent's tool is refused: both name the store rule.
    await expect(turn.getByTestId("turn-error").or(turn.getByTestId("agent-answer"))).toBeVisible({ timeout: 120_000 });
    await expect(turn).toContainText(/cửa hàng/i);
    await expect(turn.locator('[data-testid="proposal-card"]')).toHaveCount(0);
  });
});

test("API từ chối quản lý cửa hàng xem cửa hàng khác (403 forbidden_store)", async ({ request }) => {
  const res = await request.post("/api/auth/login", { data: { username: "manager_a1", password: DEMO_PASSWORD } });
  expect(res.ok()).toBeTruthy();
  const { token, user } = (await res.json()) as { token: string; user: { store_id: string } };
  const other = user.store_id === "A-CH3" ? "A-CH1" : "A-CH3";
  const denied = await request.post("/api/inventory/plan", {
    headers: { Authorization: `Bearer ${token}` },
    data: { store_id: other, categories: ["vegetable"], horizon_days: 1 },
  });
  expect(denied.status()).toBe(403);
  const body = (await denied.json()) as { error: { code: string; message_vi: string } };
  expect(body.error.code).toBe("forbidden_store");
  expect(body.error.message_vi).toMatch(/cửa hàng/);
});
