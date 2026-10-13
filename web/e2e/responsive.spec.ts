import { expect, login, runTool, test } from "./fixtures";

test("Bố cục: hai khung trên desktop, khung xếp chồng có công tắc trên điện thoại", async ({ page }, testInfo) => {
  await login(page, "owner_a");
  const chat = page.getByTestId("chat-input");
  const dashTab = page.getByTestId("tab-dashboard");
  await expect(page.getByTestId("provenance-badge")).toBeVisible();

  if (testInfo.project.name === "desktop") {
    await expect(page.getByTestId("pane-chat")).toBeHidden();
    await expect(chat).toBeVisible();
    await expect(dashTab).toBeVisible();
    const chatBox = await chat.boundingBox();
    const dashBox = await dashTab.boundingBox();
    expect(chatBox && dashBox && dashBox.x > chatBox.x + chatBox.width - 1).toBeTruthy();
  } else {
    await expect(page.getByTestId("pane-chat")).toBeVisible();
    await expect(chat).toBeVisible();
    await expect(dashTab).toBeHidden();
    await page.getByTestId("pane-dashboard").click();
    await expect(dashTab).toBeVisible();
    await expect(chat).toBeHidden();
    // No horizontal page scroll on phones, including with a full dashboard (route map, tables, tooltips).
    const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(await overflow()).toBeLessThanOrEqual(1);
    await runTool(page, "route");
    await expect(page.getByTestId("route-map")).toBeVisible();
    expect(await overflow()).toBeLessThanOrEqual(1);
    await runTool(page, "stock");
    await runTool(page, "inventory");
    expect(await overflow()).toBeLessThanOrEqual(1);
    await page.getByTestId("provenance-badge").click();
    await expect(page.getByTestId("sources-panel")).toBeVisible();
    expect(await overflow()).toBeLessThanOrEqual(1);
  }
});
