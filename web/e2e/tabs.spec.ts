import { createPanelDraft, expect, login, runTool, showPane, test } from "./fixtures";

// Shape of GET /api/provenance (provenance.describe). Kinds: public | ai_generated | derived | synthetic_code.

test("Các tab: lịch sử quyết định, mạng lưới FL, nguồn & giả định dữ liệu", async ({ page }) => {
  await login(page, "owner_a");
  await runTool(page, "inventory");
  const card = await createPanelDraft(page, "inventory", "draft-purchase");
  await card.getByTestId("proposal-approve").click();
  await expect(card.getByTestId("draft-status")).toHaveText("Đã duyệt");

  await page.getByTestId("tab-audit").click();
  const audit = page.getByTestId("audit-list");
  await expect(audit).toBeVisible();
  await expect(audit.locator("li").first()).toBeVisible();

  await page.getByTestId("tab-fl").click();
  // The FL experiments have been run (docs/experiments), so the real panel must render, never the empty state.
  const fl = page.getByTestId("fl-panel");
  await expect(fl).toBeVisible();
  await expect(page.getByTestId("fl-not-ready")).toHaveCount(0);
  await expect(fl).toContainText("Chuỗi tham gia");
  await expect(fl).toContainText("dự báo đang dùng mô hình cục bộ");

  await page.getByTestId("tab-sources").click();
  await expect(page.getByTestId("tab-sources")).toHaveText("Nguồn & giả định dữ liệu");
  const sources = page.getByTestId("sources-panel");
  await expect(sources).toBeVisible();
  // The UI's own provenance panel never falls back to the old blanket label (assumption prose is server content).
  await expect(page.getByTestId("provenance-datasets")).not.toContainText("SIMULATED");
  const assumptions = page.getByTestId("assumptions-panel");
  await expect(assumptions.locator("section").first()).toBeVisible();

  // Keyboard: arrow keys move between tabs.
  await page.getByTestId("tab-sources").focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("tab-fl")).toHaveAttribute("aria-selected", "true");
});

test("Huy hiệu nguồn dữ liệu mở tab nguồn: bộ dữ liệu có loại, giấy phép, đường dẫn an toàn", async ({ page }) => {
  await login(page, "owner_a");
  const badge = page.getByTestId("provenance-badge");
  // The badge counts the datasets of GET /api/provenance.
  await expect(badge).toContainText(/Nguồn dữ liệu\s*\d+/);
  const count = Number((await badge.textContent())?.match(/\d+/)?.[0]);
  await badge.click();
  await expect(page.getByTestId("tab-sources")).toHaveAttribute("aria-selected", "true");
  const datasets = page.getByTestId("dataset");
  await expect(datasets).toHaveCount(count);
  expect(count).toBeGreaterThan(0);
  for (const d of await datasets.all()) {
    await expect(d.getByTestId("kind-chip")).toHaveText(/Công khai|AI sinh|Chương trình mô phỏng|Tính toán|Khác/);
    await expect(d).toContainText("Giấy phép");
  }
  const links = page.getByTestId("dataset-link");
  for (const a of await links.all()) {
    await expect(a).toHaveAttribute("href", /^https?:\/\//);
    await expect(a).toHaveAttribute("rel", /noopener/);
    await expect(a).toHaveAttribute("target", "_blank");
  }
  // AI-generated datasets name the prompts they came from.
  for (const d of await page.locator('[data-testid="dataset"][data-kind="ai_generated"]').all()) {
    await expect(d).toContainText("Prompt đã dùng");
  }
  await showPane(page, "dashboard");
  await expect(page.getByTestId("provenance-datasets")).toBeVisible();
});

test("Tab nguồn: bộ dữ liệu AI sinh hiện prompt, đường dẫn không an toàn chỉ hiện dạng chữ", async ({ page }) => {
  // The live registry has no AI-generated dataset and only https URLs, so this registry is served by the test
  // to exercise those two rules; the rendering path is the same as for the real endpoint.
  await page.route(/\/api\/provenance$/, (route) =>
    route.fulfill({
      json: {
        datasets: [
          {
            id: "AI_RECIPES",
            name_vi: "Mô tả món ăn do AI sinh",
            kind: "ai_generated",
            url: "javascript:alert(1)",
            license: "Nội bộ",
            retrieved_at: "2026-10-12T08:00:00Z",
            description_vi: "Sinh bằng mô hình ngôn ngữ theo prompt đã ghi lại.",
            prompt_ids: ["P-0001"],
            prompts: [{ id: "P-0002", text: "..." }],
          },
          {
            id: "GEN_PROGRAM_V1",
            name_vi: "Mô phỏng bằng chương trình",
            kind: "synthetic_code",
            url: null,
            license: "Mã nguồn FreshMesh",
            retrieved_at: null,
            description_vi: "Sinh bằng chương trình data_sim.",
            prompt_ids: [],
          },
          {
            id: "OSM_HCMC_SITES",
            name_vi: "Vị trí từ OSM",
            kind: "derived",
            url: "https://www.openstreetmap.org/copyright",
            license: "ODbL 1.0",
            retrieved_at: null,
            description_vi: "Dẫn xuất từ OSM.",
            prompt_ids: [],
          },
        ],
      },
    }),
  );
  await login(page, "owner_a");
  await expect(page.getByTestId("provenance-badge")).toContainText("3");
  await page.getByTestId("provenance-badge").click();

  const ai = page.locator('[data-testid="dataset"][data-kind="ai_generated"]');
  await expect(ai.getByTestId("kind-chip")).toHaveText("AI sinh");
  await expect(ai).toContainText("Prompt đã dùng");
  await expect(ai).toContainText("P-0001");
  await expect(ai).toContainText("P-0002");
  // javascript: is never a link.
  await expect(ai.getByTestId("dataset-link")).toHaveCount(0);
  await expect(ai.locator("a")).toHaveCount(0);
  await expect(ai).toContainText("javascript:alert(1)");

  const sim = page.locator('[data-testid="dataset"][data-kind="simulated"]');
  await expect(sim.getByTestId("kind-chip")).toHaveText("Chương trình mô phỏng");
  await expect(sim).toContainText("không có đường dẫn");

  const derived = page.locator('[data-testid="dataset"][data-kind="computed"]');
  await expect(derived.getByTestId("kind-chip")).toHaveText("Tính toán");
  await expect(derived.getByTestId("dataset-link")).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
});
