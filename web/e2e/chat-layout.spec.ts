import type { Locator, Page } from "@playwright/test";
import { expect, forceLlm, login, showPane, test } from "./fixtures";
import { loadLongTurnData, sendChat, serveChat, type LongTurnData } from "./longTurn";

// Regression: after one long answer the composer was pushed below the viewport (the conversation grew the
// pane instead of scrolling inside it) and the user could not chat any more. For each viewport, a long turn
// (many tool steps, long sections, a long sources list, two real drafts) is served through the chat
// endpoint, then the composer must stay inside the viewport and further messages must go out.

const VIEWPORTS = [
  { width: 1440, height: 760 },
  { width: 1900, height: 850 },
  { width: 820, height: 1180 },
  { width: 390, height: 844 },
];

// Each viewport runs once: the phone in the mobile project (touch, DPR 3), the others in the desktop project.
const PHONE = 390;

let data: LongTurnData;
test.beforeAll(async ({ request }, info) => {
  data = await loadLongTurnData(request, String(info.project.use.baseURL));
});

/** Scroll offsets of the document and of the app shell (neither may move on desktop). */
const shellScroll = (page: Page) =>
  page.evaluate(() => ({
    doc: document.scrollingElement?.scrollTop ?? 0,
    app: document.querySelector("main")?.parentElement?.scrollTop ?? 0,
  }));

async function box(locator: Locator) {
  const b = await locator.boundingBox();
  expect(b, "element is rendered").not.toBeNull();
  return b!;
}

/** The composer (textarea and send button) lies fully inside the viewport. */
async function expectComposerInViewport(page: Page, vp: { width: number; height: number }) {
  for (const id of ["chat-input", "chat-send"]) {
    const b = await box(page.getByTestId(id));
    expect(b.y, `${id} top`).toBeGreaterThanOrEqual(0);
    expect(b.y + b.height, `${id} bottom`).toBeLessThanOrEqual(vp.height);
    expect(b.x, `${id} left`).toBeGreaterThanOrEqual(0);
    expect(b.x + b.width, `${id} right`).toBeLessThanOrEqual(vp.width);
  }
}

/** The newest question is visible between the top of the viewport (below the sticky switcher) and the composer. */
async function expectNewestInView(page: Page) {
  const question = await box(page.getByTestId("turn-question").last());
  const composer = await box(page.getByTestId("chat-input").locator("xpath=ancestor::form"));
  const switcher = page.getByTestId("pane-chat");
  const sw = (await switcher.isVisible()) ? await box(switcher) : null;
  const top = sw ? sw.y + sw.height : 0;
  expect(question.y).toBeGreaterThanOrEqual(top - 1);
  expect(question.y + question.height).toBeLessThanOrEqual(composer.y);
}

for (const vp of VIEWPORTS) {
  const desktop = vp.width >= 1024;

  test(`${vp.width}x${vp.height}: sau câu trả lời dài, ô nhập vẫn trong màn hình và gửi tiếp được`, async ({ page, isMobile }) => {
    test.skip(isMobile !== (vp.width === PHONE), "khung nhìn này chạy ở dự án còn lại");
    await page.setViewportSize(vp);
    await forceLlm(page, true);
    const sent = await serveChat(page, data);
    await login(page, "owner_a");
    await showPane(page, "chat");

    await sendChat(page, "Nhập rau và thịt cho mai thế nào?");
    const first = page.getByTestId("turn").first();
    await expect(first.getByTestId("agent-answer")).toBeVisible();
    await expect(first.getByTestId("proposal-card")).toHaveCount(2);
    await expect(page.getByTestId("chat-status")).toHaveText(/Trợ lý đã trả lời, 2 đề xuất chờ bạn duyệt/);

    // Measured before any further interaction: Playwright's own scrolling must not be what makes it visible.
    await expectComposerInViewport(page, vp);
    await expectNewestInView(page);
    if (desktop) {
      expect(await shellScroll(page)).toEqual({ doc: 0, app: 0 });
      // The conversation scrolls inside its own element.
      const scroller = page.getByTestId("chat-scroll");
      expect(await scroller.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    }
    const input = page.getByTestId("chat-input");
    await expect(input).toBeEnabled();
    await input.focus();
    await expect(input).toBeFocused();

    // The long answer goes below the fold: the jump button brings the end into view and then hides.
    const toNewest = page.getByTestId("scroll-to-newest");
    await expect(toNewest).toBeVisible();
    await toNewest.click();
    await expect(toNewest).toBeHidden();
    await expect(first.getByTestId("proposal-card").last()).toBeInViewport();

    // Second and third messages: each one is a new request, the input is focused again and stays on screen.
    await sendChat(page, "Còn gì cần lưu ý không?");
    await expect.poll(() => sent.length).toBe(2);
    await expect(page.getByTestId("turn")).toHaveCount(2);
    await expect(page.getByTestId("turn").nth(1).getByTestId("agent-answer")).toBeVisible();
    await expect(input).toBeFocused();
    await expect(input).toHaveValue("");
    await expectComposerInViewport(page, vp);
    await expectNewestInView(page);

    await page.getByTestId("suggested-prompt").first().click();
    await expect.poll(() => sent.length).toBe(3);
    await expect(page.getByTestId("turn").nth(2).getByTestId("agent-answer")).toBeVisible();
    await expect(input).toBeFocused();
    await expectComposerInViewport(page, vp);
    await expectNewestInView(page);
    expect(sent).toEqual(["Nhập rau và thịt cho mai thế nào?", "Còn gì cần lưu ý không?", "Nhập rau và thịt cho mai thế nào?"]);
    if (desktop) expect(await shellScroll(page)).toEqual({ doc: 0, app: 0 });

    // The dashboard shows the long turn's panels and scrolls in its own pane, not the page.
    await showPane(page, "dashboard");
    await expect(page.getByTestId("plan-table")).toBeVisible();
    const body = page.getByTestId("tab-body");
    if (desktop) {
      expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
      const b = await box(body);
      await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
      await page.mouse.wheel(0, 900);
      await expect.poll(() => body.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
      expect(await shellScroll(page)).toEqual({ doc: 0, app: 0 });
      // The chat composer did not move while the dashboard scrolled.
      await expectComposerInViewport(page, vp);
    } else {
      // Stacked layout: the page scrolls, without sideways overflow.
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    }
  });
}
