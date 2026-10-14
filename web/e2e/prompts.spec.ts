import { expect, login, runTool, showPane, test } from "./fixtures";

// "Bằng chứng prompt": the evidence of the AI calls behind AI_PARAMS_* datasets, from the real API
// (GET /api/provenance summaries + GET /api/provenance/prompts/{id}). Desktop and mobile projects both run it.

async function openSources(page: import("@playwright/test").Page) {
  await page.getByTestId("provenance-badge").click();
  await showPane(page, "dashboard");
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("provenance-datasets")).toBeVisible();
}

test("Bằng chứng prompt: mở prompt của AI_PARAMS_CATALOG, xem nguyên văn và SHA-256 đã xác minh", async ({ page }) => {
  await login(page, "owner_a");
  await openSources(page);

  const card = page.locator('[data-testid="dataset"][data-dataset-id="AI_PARAMS_CATALOG"]');
  await expect(card.getByTestId("kind-chip")).toHaveText("AI sinh");
  const toggle = card.getByTestId("prompt-evidence-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toContainText("Bằng chứng prompt");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");

  const items = card.getByTestId("prompt-evidence-item");
  await expect(items).toHaveCount(1);
  const item = items.first();
  // Task, model, time and status come from the prompt log.
  await expect(item).toContainText("catalog");
  await expect(item).toContainText("claude-haiku-5-5");
  await expect(item.getByTestId("prompt-status")).toHaveText("Được chấp nhận");
  const promptId = await item.getAttribute("data-prompt-id");
  expect(promptId).toMatch(/^P\d{8}T\d{6}-[0-9a-f]{10}$/);

  // Keyboard: the row opens the viewer with Enter; focus moves into the dialog.
  await item.focus();
  await page.keyboard.press("Enter");
  const viewer = page.getByTestId("prompt-viewer");
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole("heading", { level: 2 })).toBeFocused();
  await expect(viewer.getByTestId("prompt-viewer-id")).toHaveText(promptId!);

  const promptText = viewer.getByTestId("prompt-text-content");
  await expect(promptText).toContainText("FreshMesh");
  await expect(viewer.getByTestId("prompt-response-content")).toContainText("SKU_RAU_MUONG");
  await expect(viewer.getByTestId("prompt-response-sha-ok")).toContainText("✓");
  await expect(viewer.getByTestId("prompt-response-sha-ok")).toContainText("Đã xác minh");
  await expect(viewer.getByTestId("prompt-response-sha")).toContainText(/[0-9a-f]{64}/);
  await expect(viewer.getByTestId("prompt-text-copy")).toBeVisible();
  await expect(viewer.getByTestId("prompt-response-copy")).toBeVisible();
  await expect(viewer.getByTestId("prompt-params-content")).toContainText("max_tokens");
  // The temperature note is the registry's own text (details.temperature_note_vi), not a UI constant.
  await expect(viewer.getByTestId("prompt-notes")).toContainText("temperature");
  // Both datasets built from this prompt are named.
  await expect(viewer).toContainText("GEN_FROM_AI_PARAMS_V1");

  // Long texts scroll inside their panel: neither the page nor the dialog grows sideways.
  const overflow = await page.evaluate(() => {
    const body = document.querySelector('[data-testid="prompt-viewer-body"]') as HTMLElement;
    const pre = document.querySelector('[data-testid="prompt-response-content"]') as HTMLElement;
    return {
      page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      body: body.scrollWidth - body.clientWidth,
      preScrolls: pre.scrollHeight > pre.clientHeight,
    };
  });
  expect(overflow.page).toBeLessThanOrEqual(0);
  expect(overflow.body).toBeLessThanOrEqual(0);
  expect(overflow.preScrolls).toBe(true);

  // Pretty-print toggle only changes the view; the copy button still copies the raw text.
  const format = viewer.getByTestId("prompt-response-format");
  await format.click();
  await expect(format).toHaveAttribute("aria-pressed", "true");
  await expect(viewer.getByTestId("prompt-response-content")).toContainText('"sku_id": "SKU_RAU_MUONG"');

  // Escape closes the dialog and focus returns to the row that opened it.
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);
  await expect(item).toBeFocused();
});

test("Bằng chứng prompt: bộ dữ liệu sinh từ tham số AI liệt kê đủ 6 prompt", async ({ page }) => {
  await login(page, "owner_a");
  await openSources(page);
  const card = page.locator('[data-testid="dataset"][data-dataset-id="GEN_FROM_AI_PARAMS_V1"]');
  await card.getByTestId("prompt-evidence-toggle").click();
  await expect(card.getByTestId("prompt-evidence-item")).toHaveCount(6);
  for (const task of ["catalog", "demand", "chains", "orders", "elasticity", "lots"]) {
    await expect(card.getByTestId("prompt-evidence-item").filter({ hasText: task })).toHaveCount(1);
  }
  // Datasets without logged prompts (public data) have no evidence disclosure.
  await expect(page.locator('[data-testid="dataset"][data-kind="public"]').getByTestId("prompt-evidence")).toHaveCount(0);

  // The close button works too, on a different prompt.
  await card.getByTestId("prompt-evidence-item").filter({ hasText: "lots" }).click();
  const viewer = page.getByTestId("prompt-viewer");
  await expect(viewer.getByTestId("prompt-response-sha-ok")).toBeVisible();
  await viewer.getByTestId("prompt-viewer-close").click();
  await expect(viewer).toHaveCount(0);
});

test("Bằng chứng prompt: prompt không có trong nhật ký hiện lỗi 404 rõ ràng", async ({ page, failures }) => {
  // A well-formed id the real API does not know: the list is the real one with one id added to the catalog dataset.
  const missing = "P20990101T000000-0123456789";
  await page.route(/\/api\/provenance$/, async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { datasets: { id: string; prompts: unknown[]; prompt_ids: string[] }[] };
    for (const d of body.datasets) {
      if (d.id === "AI_PARAMS_CATALOG") {
        d.prompts = [...d.prompts, { id: missing, task: "catalog", ts: "2099-01-01T00:00:00+00:00", model: "claude-haiku-5-5", status: "accepted", attempt: 2 }];
        d.prompt_ids = [...d.prompt_ids, missing];
      }
    }
    await route.fulfill({ response: res, json: body });
  });
  failures.allow(/\/api\/provenance\/prompts\/P20990101T000000-0123456789$/, 404);

  await login(page, "owner_a");
  await openSources(page);
  const card = page.locator('[data-testid="dataset"][data-dataset-id="AI_PARAMS_CATALOG"]');
  await card.getByTestId("prompt-evidence-toggle").click();
  await card.locator(`[data-prompt-id="${missing}"]`).click();
  const viewer = page.getByTestId("prompt-viewer");
  const error = viewer.getByTestId("prompt-viewer-error");
  await expect(error).toBeVisible();
  await expect(error).toContainText("Không tìm thấy prompt này");
  await expect(error).toContainText("Không có lượt gọi AI (prompt) này trong nhật ký prompt.");
  await expect(viewer.getByTestId("prompt-text")).toHaveCount(0);
  await viewer.getByTestId("prompt-viewer-close").click();
  await expect(viewer).toHaveCount(0);
});

test("Chip 'AI sinh' cạnh số liệu dự báo mở đúng bộ dữ liệu trong tab nguồn", async ({ page }) => {
  // The real forecast payload names AI_PARAMS_CATALOG (prices, shelf life) among its datasets.
  await login(page, "owner_a");
  const panel = await runTool(page, "forecast");
  const line = panel.getByTestId("sources-line").first();
  await line.getByTestId("sources-toggle").click();
  const link = line.locator('[data-testid="kind-chip-link"][data-dataset-id="AI_PARAMS_CATALOG"]');
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("href", "#dataset-AI_PARAMS_CATALOG");
  await link.click();

  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  const card = page.locator('[data-testid="dataset"][data-dataset-id="AI_PARAMS_CATALOG"]');
  await expect(card.locator("h3")).toBeFocused();
  await expect(card.getByTestId("prompt-evidence-toggle")).toHaveAttribute("aria-expanded", "true");
  await expect(card.getByTestId("prompt-evidence-item")).toHaveCount(1);
});
