import { test as base, expect, type Page } from "@playwright/test";

/**
 * Every test fails on:
 *  - a console.error from the app;
 *  - an uncaught page error;
 *  - a 4xx/5xx response (or failed request) to the app's own origin,
 * unless the test declares it with `failures.allow(...)`. Third-party requests (OSM tiles) are ignored:
 * tile servers can rate-limit headless browsers and tiles are aborted on pan/zoom.
 */
interface Allowed {
  url: RegExp;
  status: number;
}

export interface FailureGuard {
  allow(url: RegExp, status: number): void;
}

export const test = base.extend<{ failures: FailureGuard }>({
  failures: [
    async ({ page, baseURL }, use, testInfo) => {
      const origin = new URL(baseURL ?? "http://localhost:3100").origin;
      const allowed: Allowed[] = [];
      const problems: string[] = [];
      const isAllowed = (url: string, status: number) => allowed.some((a) => a.status === status && a.url.test(url));

      page.on("console", (msg) => {
        if (msg.type() !== "error") return;
        const text = msg.text();
        // Network failures are reported (and filtered) by the response handlers below.
        if (text.startsWith("Failed to load resource")) return;
        problems.push(`console.error: ${text}`);
      });
      page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
      page.on("response", (res) => {
        const url = res.url();
        if (!url.startsWith(origin) || res.status() < 400) return;
        if (!isAllowed(url, res.status())) problems.push(`HTTP ${res.status()} ${res.request().method()} ${url}`);
      });
      page.on("requestfailed", (req) => {
        const url = req.url();
        if (!url.startsWith(origin)) return;
        const failure = req.failure()?.errorText ?? "";
        // Aborted by the app itself (AbortController on unmount / new request).
        if (/ERR_ABORTED|NS_BINDING_ABORTED|cancelled/i.test(failure)) return;
        problems.push(`request failed: ${req.method()} ${url} ${failure}`);
      });

      await use({ allow: (url, status) => allowed.push({ url, status }) });

      if (problems.length) {
        await testInfo.attach("console-and-network-problems", { body: problems.join("\n"), contentType: "text/plain" });
      }
      expect(problems, "console errors / failed requests during the test").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export const DEMO_PASSWORD = "demo123";

/** Chat tests need a real LLM key on the gateway; they are skipped (and reported as skipped) otherwise. */
export const HAS_LLM = Boolean(process.env.FRESHMESH_E2E_LLM);
export const NEEDS_LLM = "cần khóa LLM thật (đặt FRESHMESH_E2E_LLM=1 và ANTHROPIC_API_KEY cho API)";

/** Exact setup message of the LLM-unavailable state. */
export const LLM_SETUP_VI = "Chưa cấu hình khóa LLM: đặt ANTHROPIC_API_KEY cho API rồi khởi động lại.";

export const NO_RAW_VALUES = /NaN|null|undefined/;

export async function login(page: Page, username = "owner_a", password = DEMO_PASSWORD) {
  await page.goto("/login");
  await page.getByTestId("login-username").fill(username);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("provenance-badge")).toBeVisible();
  await expect(page.getByTestId("direct-tools")).toBeAttached();
}

/** On phones the panes are stacked behind a segmented switch. */
export async function showPane(page: Page, pane: "chat" | "dashboard") {
  const toggle = page.getByTestId(`pane-${pane}`);
  if (await toggle.isVisible()) await toggle.click();
}

export type ToolSlot = "forecast" | "inventory" | "stock" | "route";

const PANEL_OF: Record<ToolSlot, string> = {
  forecast: "forecast-chart",
  inventory: "plan-table",
  stock: "stock-comparison",
  route: "route-panel",
};

/** Runs one direct tool (REST endpoint, no LLM) from its dashboard button and returns its panel. */
export async function runTool(page: Page, slot: ToolSlot) {
  await showPane(page, "dashboard");
  await page.getByTestId("tab-dashboard").click();
  const button = page.getByTestId(`tool-${slot}`);
  await button.click();
  await expect(button).toHaveAttribute("data-state", "ready", { timeout: 120_000 });
  const panel = page.getByTestId(PANEL_OF[slot]);
  await expect(panel).toBeVisible();
  await expect(page.getByTestId(`tool-error-${slot}`)).toHaveCount(0);
  return panel;
}

/** Creates a draft from a tool panel's button and returns its proposal card. */
export async function createPanelDraft(page: Page, slot: ToolSlot, buttonTestId: string) {
  const panel = page.getByTestId(PANEL_OF[slot]);
  const cards = panel.getByTestId("proposal-card");
  const before = await cards.count();
  await panel.getByTestId(buttonTestId).click();
  const card = cards.nth(before);
  await expect(card.getByTestId("draft-status")).toHaveText("Bản nháp, chờ duyệt");
  await expect(panel.getByTestId("panel-draft-error")).toHaveCount(0);
  return card;
}

/** Health as the gateway reports it, with the LLM flag forced (deterministic with or without a key). */
export async function forceLlm(page: Page, llm: boolean) {
  await page.route(/\/api\/health$/, async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as Record<string, unknown>;
    await route.fulfill({ response: res, json: { ...body, llm } });
  });
}
