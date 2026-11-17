import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const fixture = fileURLToPath(new URL("../../downlink/common-cause.json", import.meta.url));

test("inspect an episode and run the shared query", async ({ page }, info) => {
  await page.goto("./");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await expect(page.locator("#diagnosis-state")).toHaveText("Resolved");
  await expect(page.locator("#component")).toContainText("sun1");
  await expect(page.locator(".event-marker")).toHaveCount(1);
  await expect(page.locator("#notice")).toBeHidden();
  await expect.poll(() => page.locator("#wiring canvas").evaluateAll(canvases => {
    let power = 0;
    let data = 0;
    for (const canvas of canvases) {
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
      for (let offset = 0; offset < pixels.length; offset += 4) {
        if (pixels[offset + 3] < 230) continue;
        const [r, g, b] = pixels.subarray(offset, offset + 3);
        if (Math.abs(r - 143) + Math.abs(g - 168) + Math.abs(b - 191) < 12) power += 1;
        if (Math.abs(r - 128) + Math.abs(g - 192) + Math.abs(b - 188) < 12) data += 1;
      }
    }
    return Math.min(power, data);
  })).toBeGreaterThan(5);
  await page.screenshot({ path: info.outputPath("desktop.png") });

  await page.locator(".console > summary").click();
  await page.selectOption("#preset", "rank");
  await page.getByRole("button", { name: "Run query" }).click();
  await expect(page.locator("#query-result tbody tr").first()).toContainText("REG_B");
  await page.fill("#query", "MATCH (n) DETACH DELETE n");
  await page.getByRole("button", { name: "Run query" }).click();
  await expect(page.locator("#query-status")).toContainText("The console accepts graph reads");
});

test("open a downlink and keep the current graph if import fails", async ({ page }) => {
  await page.goto("./");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await page.locator("#file").setInputFiles({
    name: "broken.json",
    mimeType: "application/json",
    buffer: Buffer.from('{"nodes":[],"rels":[{}]}'),
  });
  await expect(page.locator("#notice")).toContainText("invalid relationship");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");

  await page.locator("#file").setInputFiles(fixture);
  await expect(page.locator("#source")).toHaveText("Imported downlink");
  await page.getByRole("button", { name: "Restore fixture" }).click();
  await expect(page.locator("#source")).toHaveText("Synthetic fixture");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await page.selectOption("#part", "Bus:I2C-1");
  await expect(page.getByRole("heading", { name: "Impact of I2C-1" })).toBeVisible();
  await expect(page.locator("#component")).toContainText("epsmon");
});

test("fit a small screen without page overflow", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath("mobile.png") });
});
