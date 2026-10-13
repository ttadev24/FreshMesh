import { expect, forceLlm, HAS_LLM, LLM_SETUP_VI, login, NEEDS_LLM, runTool, showPane, test } from "./fixtures";

// Chat is the real LLM agent only: no canned flows, no scripted fallback. Without a key the UI shows a
// setup state; the direct tool panels keep working.

test("Không có khóa LLM: trạng thái cài đặt tiếng Việt, khung chat khóa, công cụ trực tiếp vẫn chạy", async ({ page }) => {
  await forceLlm(page, false);
  await login(page, "owner_a");
  await showPane(page, "chat");
  const setup = page.getByTestId("llm-setup");
  await expect(setup).toBeVisible();
  await expect(setup).toContainText(LLM_SETUP_VI);
  await expect(page.getByTestId("llm-badge")).toBeVisible();
  await expect(page.getByTestId("chat-input")).toBeDisabled();
  const prompts = page.getByTestId("suggested-prompt");
  await expect(prompts.first()).toBeVisible();
  for (const p of await prompts.all()) await expect(p).toBeDisabled();
  // No canned answers or flow buttons anywhere.
  await expect(page.getByTestId("flow-1")).toHaveCount(0);
  await expect(page.getByTestId("turn")).toHaveCount(0);

  const chart = await runTool(page, "forecast");
  await expect(chart.locator("canvas").first()).toBeVisible();
});

test("Khóa LLM bị gỡ giữa phiên (503 llm_unavailable): báo lỗi cài đặt, không có câu trả lời giả", async ({ page, failures }) => {
  failures.allow(/\/api\/agent\/chat$/, 503);
  await forceLlm(page, true);
  await page.route(/\/api\/agent\/chat$/, (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "llm_unavailable", message_vi: LLM_SETUP_VI } }),
    }),
  );
  await login(page, "owner_a");
  await showPane(page, "chat");
  // A suggestion is an ordinary chat message sent to the agent.
  await page.getByTestId("suggested-prompt").first().click();
  const turn = page.getByTestId("turn").last();
  await expect(turn.getByTestId("turn-error")).toContainText(LLM_SETUP_VI);
  await expect(turn.getByTestId("agent-answer")).toHaveCount(0);
  await expect(page.getByTestId("llm-setup")).toBeVisible();
  await expect(page.getByTestId("chat-input")).toBeDisabled();
});

test.describe("Trợ lý LLM thật", () => {
  test.skip(!HAS_LLM, NEEDS_LLM);

  test("câu gợi ý đi qua tác tử thật: các bước công cụ, khuôn 5 mục và nguồn dữ liệu", async ({ page }) => {
    await login(page, "owner_a");
    await showPane(page, "chat");
    await expect(page.getByTestId("llm-setup")).toHaveCount(0);
    await page.getByTestId("suggested-prompt").first().click();
    const turn = page.getByTestId("turn").last();
    await expect(turn.getByTestId("step-list")).toBeVisible();
    const answer = turn.getByTestId("agent-answer");
    await expect(answer).toBeVisible({ timeout: 180_000 });
    await expect(turn.getByTestId("turn-error")).toHaveCount(0);
    await expect(turn.getByTestId("tool-step").first()).toBeVisible();
    for (const section of ["Đề xuất", "Vì sao", "Độ tin cậy", "Giả định", "Việc cần bạn duyệt", "Nguồn dữ liệu"]) {
      await expect(answer.getByText(section, { exact: true })).toBeVisible();
    }
    await expect(answer.getByTestId("answer-sources")).not.toBeEmpty();
  });

  test("câu hỏi tự gõ được stream thành các bước rồi trả lời theo khuôn", async ({ page }) => {
    await login(page, "owner_a");
    await showPane(page, "chat");
    await page.getByTestId("chat-input").fill("hello");
    await page.getByTestId("chat-send").click();
    const turn = page.getByTestId("turn").last();
    await expect(turn.getByTestId("agent-answer").or(turn.getByTestId("turn-error"))).toBeVisible({ timeout: 180_000 });
    // The real agent answers free text; never the old "chỉ hiểu 3 luồng" scripted refusal.
    await expect(turn).not.toContainText(/kịch bản|chỉ hiểu 3 luồng/i);
    await expect(turn.getByTestId("turn-error")).toHaveCount(0);
  });
});
