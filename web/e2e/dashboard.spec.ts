import { expect, login, NO_RAW_VALUES, runTool, test } from "./fixtures";

// Direct tool panels: real REST computations for the selected store, from explicit buttons (no LLM).
// Every panel names the data behind it (sources / source_labels_vi) and the endpoint that computed it.

test.beforeEach(async ({ page }) => {
  await login(page, "owner_a");
  await page.getByTestId("store-select").selectOption("A-CH3");
});

async function expectSources(panel: import("@playwright/test").Locator, endpoint: string) {
  const line = panel.getByTestId("sources-line");
  await expect(line).toContainText("Nguồn dữ liệu");
  // The endpoint that computed the panel stays visible next to the collapsed sources.
  const computedBy = line.getByText("tính bởi");
  await expect(computedBy).toBeVisible();
  await expect(computedBy).toContainText(endpoint);
  // Compact by default ("Nguồn dữ liệu (N)"); expanding shows every labelled dataset.
  const toggle = line.getByTestId("sources-toggle");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  // Provenance from the API: at least one labelled dataset, never a placeholder.
  const refs = line.getByTestId("source-ref");
  await expect(refs.first()).toBeVisible();
  await expect(toggle).toContainText(`(${await refs.count()})`);
  await expect(line).not.toContainText(NO_RAW_VALUES);
}

test("Dự báo: biểu đồ dải P10 đến P90, độ tin cậy và nguồn dữ liệu", async ({ page }) => {
  const chart = await runTool(page, "forecast");
  await expect(chart.locator("canvas").first()).toBeVisible();
  await expect(chart.getByTestId("confidence-badge")).toHaveText(/Cao|Trung bình|Thấp/);
  await expectSources(chart, "/api/forecast");
});

test("3 phương án nhập: bảng An toàn / Cân bằng / Tiết kiệm có tiền và nguồn", async ({ page }) => {
  const plans = await runTool(page, "inventory");
  await expect(plans.locator("tbody > tr[data-plan]")).toHaveCount(3);
  for (const label of ["An toàn", "Cân bằng", "Tiết kiệm"]) await expect(plans.getByText(label).first()).toBeVisible();
  await expect(plans.locator("tbody > tr[data-plan]").first()).toContainText("đ");
  await expect(plans.locator('tr[data-recommended="true"]')).toHaveCount(1);
  await expectSources(plans, "/api/inventory/plan");
});

test("Giảm giá hay điều chuyển: so sánh bằng tiền có nguồn", async ({ page }) => {
  const panel = await runTool(page, "stock");
  await expect(panel).toContainText("đ");
  await expect(page.getByTestId("stock-summary")).toBeVisible();
  await expectSources(panel, "/api/transfer/plan");
  await expect(panel).not.toContainText(NO_RAW_VALUES);
});

test("Lộ trình: bản đồ OSM có đường đi của xe, cửa hàng, ghi chú bộ nhớ đệm", async ({ page }) => {
  const response = page.waitForResponse((r) => /\/api\/routing\/plan$/.test(r.url()) && r.request().method() === "POST");
  const panel = await runTool(page, "route");
  const plan = (await (await response).json()) as { cached?: boolean; solved_at?: string | null };
  const map = page.getByTestId("route-map");
  await expect(map.locator(".leaflet-container")).toBeVisible();
  // Vehicle polylines are SVG paths in Leaflet's overlay pane.
  const paths = map.locator(".leaflet-overlay-pane path.leaflet-interactive");
  await expect.poll(async () => paths.count()).toBeGreaterThan(0);
  await expect(map.locator(".leaflet-control-attribution")).toContainText("OpenStreetMap");
  await expect(page.getByTestId("vehicle-route").first()).toBeVisible();
  await expect(page.getByTestId("route-summary")).toContainText("km");
  // Cached results say so, with the solve time when the gateway knows it (null for older cache files).
  const note = page.getByTestId("route-solve-note");
  await expect(note).toHaveText(plan.cached ? /^Từ bộ nhớ đệm/ : /^Vừa giải/);
  if (plan.solved_at) await expect(note).toContainText("giải lúc");
  else if (plan.cached) await expect(note).toContainText("không ghi thời điểm giải");
  await expectSources(panel, "/api/routing/plan");
});

test("Đổi cửa hàng: kết quả tính toán không lẫn giữa các cửa hàng", async ({ page }) => {
  await runTool(page, "inventory");
  await page.getByTestId("store-select").selectOption("A-CH1");
  await expect(page.getByTestId("plan-table")).toHaveCount(0);
  await expect(page.getByTestId("direct-tools")).toContainText("CH1");
});
