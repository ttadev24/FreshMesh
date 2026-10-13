import { expect, forceLlm, login, showPane, test } from "./fixtures";
import { loadLongTurnData, regionOf, sendChat, serveChat, shortTurnSse, type LongTurnData } from "./longTurn";

// A long answer stays readable: Đề xuất and Việc cần bạn duyệt are always shown, Vì sao / Độ tin cậy /
// Giả định are disclosures (Vì sao open), the sources line and the finished tool steps are one compact line
// each, and the suggested questions shrink to one row once the conversation has turns.

test.skip(({ isMobile }) => isMobile, "kiểm tra hành vi, chạy một lần trong dự án desktop");

let data: LongTurnData;
test.beforeAll(async ({ request }, info) => {
  data = await loadLongTurnData(request, String(info.project.use.baseURL));
});

test.beforeEach(async ({ page }) => {
  await forceLlm(page, true);
});

test("Các mục của câu trả lời: mặc định mở / đóng, aria-expanded đổi khi bấm và bằng bàn phím", async ({ page }) => {
  await serveChat(page, data);
  await login(page, "owner_a");
  await showPane(page, "chat");
  await sendChat(page, "Nhập rau và thịt cho mai thế nào?");
  const turn = page.getByTestId("turn").first();
  const answer = turn.getByTestId("agent-answer");
  await expect(answer).toBeVisible();

  // Always shown: the recommendation and the review request, no toggle.
  for (const name of ["Đề xuất", "Việc cần bạn duyệt"]) {
    const section = answer.locator(`[data-section="${name}"]`);
    await expect(section.getByText(name, { exact: true })).toBeVisible();
    await expect(section.getByTestId("section-toggle")).toHaveCount(0);
  }
  await expect(answer.locator('[data-section="Đề xuất"]')).toContainText("Cân bằng");
  await expect(answer.locator('[data-section="Việc cần bạn duyệt"]')).toContainText("Duyệt một trong hai bản nháp");

  // Disclosures: Vì sao open, Độ tin cậy and Giả định closed.
  const expected = { "Vì sao": "true", "Độ tin cậy": "false", "Giả định": "false" } as const;
  for (const [name, open] of Object.entries(expected)) {
    const section = answer.locator(`[data-section="${name}"]`);
    const toggle = section.getByTestId("section-toggle");
    await expect(toggle).toHaveAttribute("aria-expanded", open);
    const region = await regionOf(page, toggle);
    if (open === "true") await expect(region).toBeVisible();
    else await expect(region).toBeHidden();
    // A closed section still names itself and previews its first line.
    await expect(toggle.getByText(name, { exact: true })).toBeVisible();
  }

  const conf = answer.locator('[data-section="Độ tin cậy"]').getByTestId("section-toggle");
  const confRegion = await regionOf(page, conf);
  await conf.click();
  await expect(conf).toHaveAttribute("aria-expanded", "true");
  await expect(confRegion).toBeVisible();
  await expect(confRegion).toContainText("Độ phủ dự báo 7 ngày");
  await conf.click();
  await expect(conf).toHaveAttribute("aria-expanded", "false");
  await expect(confRegion).toBeHidden();
  // Keyboard: Enter and Space toggle the focused button.
  await conf.focus();
  await page.keyboard.press("Enter");
  await expect(conf).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Space");
  await expect(conf).toHaveAttribute("aria-expanded", "false");

  // Sources: one line "Nguồn dữ liệu (N)" that expands to the labelled chips.
  const sources = answer.getByTestId("answer-sources");
  const sourcesToggle = sources.getByTestId("sources-toggle");
  await expect(sourcesToggle).toHaveAttribute("aria-expanded", "false");
  await expect(sourcesToggle.getByText("Nguồn dữ liệu", { exact: true })).toBeVisible();
  await expect(sourcesToggle).toContainText(`(${data.sources.length})`);
  await expect(sources.getByTestId("source-ref").first()).toBeHidden();
  await sourcesToggle.click();
  await expect(sourcesToggle).toHaveAttribute("aria-expanded", "true");
  await expect(sources.getByTestId("source-ref")).toHaveCount(data.sources.length);
  for (const ref of await sources.getByTestId("source-ref").all()) await expect(ref).toBeVisible();
  await expect(sources).toContainText(data.sourceLabels[0]);

  // Finished tool steps: one line "Đã chạy N bước công cụ" that expands to the full list.
  const steps = turn.getByTestId("steps-toggle");
  await expect(steps).toHaveText("Đã chạy 10 bước công cụ");
  await expect(steps).toHaveAttribute("aria-expanded", "false");
  await expect(turn.getByTestId("tool-step").first()).toBeHidden();
  await steps.click();
  await expect(steps).toHaveAttribute("aria-expanded", "true");
  await expect(turn.getByTestId("tool-step")).toHaveCount(10);
  for (const step of await turn.getByTestId("tool-step").all()) await expect(step).toBeVisible();
});

test("Gợi ý câu hỏi: đủ danh sách khi trống, một hàng gọn sau lượt đầu", async ({ page }) => {
  await serveChat(page, data);
  await login(page, "owner_a");
  await showPane(page, "chat");
  const scroller = page.getByTestId("chat-scroll");
  const composer = page.getByTestId("chat-input").locator("xpath=ancestor::form");

  // Empty conversation: the full list sits in the empty state, not in the composer.
  await expect(scroller.getByTestId("suggested-prompt")).toHaveCount(4);
  for (const p of await scroller.getByTestId("suggested-prompt").all()) await expect(p).toBeVisible();
  await expect(composer.getByTestId("suggested-prompt")).toHaveCount(0);

  await scroller.getByTestId("suggested-prompt").nth(1).click();
  await expect(page.getByTestId("turn").first().getByTestId("agent-answer")).toBeVisible();

  // After the first turn: a single row in the composer, no list in the conversation.
  await expect(scroller.getByTestId("suggested-prompt")).toHaveCount(0);
  const chips = composer.getByTestId("suggested-prompt");
  await expect(chips).toHaveCount(4);
  const first = (await chips.first().boundingBox())!;
  for (const chip of await chips.all()) {
    const b = await chip.boundingBox();
    expect(b, "chip rendered").not.toBeNull();
    expect(Math.abs(b!.y - first.y)).toBeLessThan(1);
    expect(b!.height).toBeLessThan(32);
  }
  const strip = (await composer.locator("ul").boundingBox())!;
  expect(strip.height).toBeLessThan(36);
  // The whole composer stays compact (strip, input, hint).
  expect((await composer.boundingBox())!.height).toBeLessThan(150);
});

test("Số chưa kiểm chứng nằm trong mục đóng: mục đó tự mở và số được tô màu", async ({ page }) => {
  await serveChat(page, null, (message) => shortTurnSse(message, "37,5%"));
  await login(page, "owner_a");
  await showPane(page, "chat");
  await sendChat(page, "Tỉ lệ hàng bỏ tuần này?");
  const answer = page.getByTestId("agent-answer");
  await expect(answer.getByTestId("unverified-flag")).toContainText("Có 1 số liệu chưa kiểm chứng");
  const assumptions = answer.locator('[data-section="Giả định"]');
  await expect(assumptions.getByTestId("section-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(assumptions.locator("mark")).toBeVisible();
  await expect(assumptions.locator("mark")).toContainText("37,5%");
  // Sections without a flagged number keep their default.
  await expect(answer.locator('[data-section="Độ tin cậy"]').getByTestId("section-toggle")).toHaveAttribute("aria-expanded", "false");
});

test("Ô nhập: Shift+Enter xuống dòng không gửi, tự cao lên tối đa khoảng 4 dòng rồi cuộn", async ({ page }) => {
  const sent = await serveChat(page, null);
  await login(page, "owner_a");
  await showPane(page, "chat");
  const input = page.getByTestId("chat-input");
  const height = () => input.evaluate((el) => el.getBoundingClientRect().height);
  await input.click();
  const oneLine = await height();
  await page.keyboard.type("Dòng một");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.type("Dòng hai");
  await expect(input).toHaveValue("Dòng một\nDòng hai");
  expect(sent).toEqual([]);
  expect(await height()).toBeGreaterThan(oneLine);

  // Many lines: the textarea stops at about four lines and scrolls inside.
  await input.fill(Array.from({ length: 9 }, (_, i) => `Dòng ${i + 1}`).join("\n"));
  const capped = await height();
  expect(capped).toBeGreaterThan(oneLine * 2);
  expect(capped).toBeLessThanOrEqual(110);
  expect(await input.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  const b = (await input.boundingBox())!;
  expect(b.y + b.height).toBeLessThanOrEqual(page.viewportSize()!.height);

  // Enter sends the whole text and the textarea shrinks back to one line.
  await input.press("Enter");
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toContain("Dòng 9");
  await expect(input).toHaveValue("");
  await expect.poll(height).toBe(oneLine);
});
