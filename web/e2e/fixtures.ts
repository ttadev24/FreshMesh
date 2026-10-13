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

export async function login(page: Page, username = "owner_a", password = DEMO_PASSWORD) {
  await page.goto("/login");
  await page.getByTestId("login-username").fill(username);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("simulated-badge")).toBeVisible();
  await expect(page.getByTestId("flow-1")).toBeVisible();
}

/** On phones the panes are stacked behind a segmented switch. */
export async function showPane(page: Page, pane: "chat" | "dashboard") {
  const toggle = page.getByTestId(`pane-${pane}`);
  if (await toggle.isVisible()) await toggle.click();
}

/** Runs a demo flow and waits for the final answer of that turn. */
export async function runFlow(page: Page, flow: 1 | 2 | 3) {
  await showPane(page, "chat");
  const turns = page.getByTestId("turn");
  const before = await turns.count();
  await page.getByTestId(`flow-${flow}`).click();
  const turn = turns.nth(before);
  await expect(turn.getByTestId("agent-answer")).toBeVisible({ timeout: 120_000 });
  await expect(turn.getByTestId("turn-error")).toHaveCount(0);
  return turn;
}
