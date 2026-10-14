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

test("Lộ trình: bản đồ VietMap có đường đi của xe, cửa hàng, ghi chú bộ nhớ đệm", async ({ page }) => {
  const response = page.waitForResponse((r) => /\/api\/routing\/plan$/.test(r.url()) && r.request().method() === "POST");
  const panel = await runTool(page, "route");
  const plan = (await (await response).json()) as { cached?: boolean; solved_at?: string | null };
  const map = page.getByTestId("route-map");
  // Needs NEXT_PUBLIC_VIETMAP_API_KEY at build time: without it the panel says so instead of drawing a map.
  await expect(map.getByTestId("map-key-missing")).toHaveCount(0);
  await expect(map.locator(".vietmapgl-canvas")).toBeVisible();
  // Vehicle paths + markers are GeoJSON layers: the map flags them once the style loaded and the layers exist.
  const canvasHost = map.locator(".vietmapgl-map");
  await expect(canvasHost).toHaveAttribute("data-layers-ready", "true");
  await expect.poll(async () => Number(await canvasHost.getAttribute("data-paths"))).toBeGreaterThan(0);
  await expect.poll(async () => Number(await canvasHost.getAttribute("data-markers"))).toBeGreaterThan(0);
  await expect(map.locator(".vietmapgl-ctrl-attrib")).toBeVisible();
  // The note says whether the drawn paths follow roads (API has FRESHMESH_VIETMAP_ROUTE_KEY) or are straight segments.
  const pathNote = page.getByTestId("route-path-note");
  const source = await pathNote.getAttribute("data-path-source");
  expect(["road", "partial", "straight"]).toContain(source);
  await expect(pathNote).toContainText(source === "road" ? "đường bộ thật" : source === "partial" ? "Một phần" : "nối thẳng");
  await expect(page.getByTestId("vehicle-route").first()).toBeVisible();
  await expect(page.getByTestId("route-summary")).toContainText("km");
  // Cached results say so, with the solve time when the gateway knows it (null for older cache files).
  const note = page.getByTestId("route-solve-note");
  await expect(note).toHaveText(plan.cached ? /^Từ bộ nhớ đệm/ : /^Vừa giải/);
  if (plan.solved_at) await expect(note).toContainText("giải lúc");
  else if (plan.cached) await expect(note).toContainText("không ghi thời điểm giải");
  await expectSources(panel, "/api/routing/plan");
});

test("Lộ trình: nút phóng to toàn màn hình giữ thanh thông số nổi phía trên bản đồ", async ({ page }) => {
  await runTool(page, "route");
  const button = page.locator(".vietmapgl-ctrl-fullscreen, .vietmapgl-ctrl-shrink"); // the SDK swaps the class while fullscreen
  await expect(button).toHaveAttribute("title", "Phóng to toàn màn hình");
  await button.click();
  // The panel shell (summary bar + map) is the fullscreen element, so the bar is still there, over the map.
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.hasAttribute("data-map-shell") ?? false)).toBe(true);
  const summary = page.getByTestId("route-summary");
  for (const label of ["Số xe", "Quãng đường", "Mỗi đơn một chuyến", "Tiết kiệm", "Đơn nguy cơ"]) await expect(summary).toContainText(label);
  const box = async (id: string) => (await page.getByTestId(id).boundingBox())!;
  const [bar, map] = [await box("route-summary"), await box("route-map")];
  expect(bar.y).toBeGreaterThanOrEqual(map.y);
  expect(bar.y + bar.height).toBeLessThan(map.y + map.height / 2);
  expect(map.height).toBeGreaterThan(bar.height * 4);
  await expect(button).toHaveAttribute("title", "Thoát toàn màn hình");
  await button.click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
  await expect(summary).toBeVisible();
});

test("Lộ trình: chọn xem riêng từng xe trên bản đồ", async ({ page }) => {
  await runTool(page, "route");
  const picker = page.getByTestId("vehicle-focus");
  const all = picker.getByRole("button", { name: "Tất cả xe" });
  const xe2 = picker.getByRole("button", { name: /Xe 2/ });
  await expect(all).toHaveAttribute("aria-pressed", "true");
  await xe2.click();
  await expect(xe2).toHaveAttribute("aria-pressed", "true");
  await expect(all).toHaveAttribute("aria-pressed", "false");
  await xe2.click(); // same chip again = back to every vehicle
  await expect(all).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".vietmapgl-canvas")).toBeVisible();
});

test("Đổi cửa hàng: kết quả tính toán không lẫn giữa các cửa hàng", async ({ page }) => {
  await runTool(page, "inventory");
  await page.getByTestId("store-select").selectOption("A-CH1");
  await expect(page.getByTestId("plan-table")).toHaveCount(0);
  await expect(page.getByTestId("direct-tools")).toContainText("CH1");
});
