import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const fixture = process.env.COMMONCAUSE_DOWNLINK
  || fileURLToPath(new URL("../../downlink/common-cause.json", import.meta.url));

test("inspect an episode and run the shared query", async ({ page }, info) => {
  await page.goto("./");
  await page.locator("#workspace > summary").click();
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
  await page.locator("#workspace > summary").click();
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
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath("mobile.png") });
});

test("switch simulations and share a combined fault", async ({ page }) => {
  await page.goto("./");
  await page.locator("#workspace > summary").click();
  const picker = page.locator("#simulation");
  await expect(picker).toHaveValue("cubesat:F1");
  await expect(page.locator("#simulation-score")).toContainText("9/9");
  await expect(page.locator("#simulation-score")).toContainText("2/9");

  await picker.selectOption("cubesat:F2");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("I2C-1");
  await picker.selectOption("cubesat:F9");
  await expect(page.locator("#diagnosis .rank-table:not(.candidate-table) tbody tr")).toHaveCount(2);
  await expect(page.locator("#diagnosis .rank-table:not(.candidate-table) tbody tr").nth(1)).toContainText("I2C-3");
  await expect(page).toHaveURL(/case=cubesat%3AF9$/);
  await page.reload();
  await page.locator("#workspace > summary").click();
  await expect(picker).toHaveValue("cubesat:F9");
  await expect(page.locator("#diagnosis .rank-table:not(.candidate-table) tbody tr")).toHaveCount(2);

  await picker.selectOption("quadcopter:bec-brownout");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("BEC_5V");
  await expect(page.locator("#simulation-score")).toContainText("3/3");
  await expect(page.getByRole("link", { name: "Download simulated readings" }))
    .toHaveAttribute("href", /simulations\/quadcopter\.jsonl$/);
});

test("show the healthy devices against each candidate and the voltage sag", async ({ page }) => {
  await page.goto("./");
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  const candidates = page.locator("#diagnosis .candidates tbody tr");
  await expect(candidates.first()).toContainText("REG_B");
  await expect(candidates.first()).toContainText("none");
  await expect(candidates.filter({ hasText: "I2C-1" })).toContainText("epsmon, thermal");
  await expect(page.locator("#precursors")).toBeVisible();
  await page.locator("#precursors > summary").click();
  await expect(page.locator("#changes tbody tr").filter({ hasText: "eps.regb.voltage" }))
    .toContainText("3.28");
});

test("open the committed downlink from the case picker and restore it", async ({ page }) => {
  await page.goto("./?case=downlink");
  await page.locator("#workspace > summary").click();
  const picker = page.locator("#simulation");
  await expect(picker).toHaveValue("downlink");
  await expect(page.locator("#metadata")).toHaveText("cubesat-bench / f1-fixture");
  await expect(page.locator("#simulation-results")).toBeHidden();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");

  await picker.selectOption("cubesat:F2");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("I2C-1");
  await picker.selectOption("downlink");
  await expect(page).toHaveURL(/case=downlink$/);
  await expect(page.locator("#metadata")).toHaveText("cubesat-bench / f1-fixture");

  await page.locator("#file").setInputFiles(fixture);
  await expect(page.locator("#source")).toHaveText("Imported downlink");
  await page.getByRole("button", { name: "Restore fixture" }).click();
  await expect(picker).toHaveValue("downlink");
  await expect(page.locator("#metadata")).toHaveText("cubesat-bench / f1-fixture");
});

test("keep a part picked while an episode is still loading", async ({ page }) => {
  // Slow every Relate worker reply so the episode is still loading when the part is picked.
  await page.addInitScript(() => {
    const Native = window.Worker;
    window.Worker = class extends Native {
      set onmessage(handler) {
        super.onmessage = event => setTimeout(() => handler(event), 300);
      }
    };
  });
  await page.goto("./?case=downlink");
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#metadata")).toHaveText("cubesat-bench / f1-fixture");
  await page.selectOption("#part", "Bus:I2C-1");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await expect(page.locator("#changes tbody tr").first()).toBeAttached();
  await page.waitForTimeout(1000);
  await expect(page.locator("#part")).toHaveValue("Bus:I2C-1");
  await expect(page.locator("#component")).toContainText("Impact of I2C-1");
});

test("identify a newly captured and replayed virtual bench downlink", async ({ page }) => {
  const virtual = process.env.COMMONCAUSE_VIRTUAL_DOWNLINK;
  test.skip(!virtual, "requires a downlink from the virtual bench workflow");
  await page.goto("./");
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await page.locator("#file").setInputFiles(virtual);
  await expect(page.locator("#source")).toHaveText("Simulated bench");
  await expect(page.locator("#metadata")).toContainText("virtual-f1");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await expect(page.locator("#diagnosis-state")).toHaveText("Resolved");
  await page.getByRole("button", { name: "Restore fixture" }).click();
  await expect(page.locator("#source")).toHaveText("Synthetic fixture");
});

test("inspect the recorded 36-injection session and switch its episodes", async ({ page }) => {
  await page.goto("./");
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await page.getByRole("button", { name: "Open 36-fault session" }).click();
  await expect(page.locator("#source")).toHaveText("Simulated bench");
  await expect(page.locator("#metadata")).toContainText("virtual-matrix-36");
  await expect(page.locator("#episode option")).toHaveCount(36);
  await expect(page.locator("#diagnosis .rank-table:not(.candidate-table) tbody tr")).toHaveCount(2);
  await expect(page.locator("#diagnosis-state")).toHaveText("Resolved");
  await page.selectOption("#episode", "dx:virtual-matrix-36:1");
  await expect(page.locator("#diagnosis .rank-table:not(.candidate-table) tbody tr")).toHaveCount(0);
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await expect(page.locator("#source")).toHaveText("Simulated bench");
  await page.getByRole("button", { name: "Restore fixture" }).click();
  await expect(page.locator("#source")).toHaveText("Synthetic fixture");
});

test("inspect a verified recovery attempt from a newly captured downlink", async ({ page }) => {
  const recovery = process.env.COMMONCAUSE_RECOVERY_DOWNLINK;
  test.skip(!recovery, "requires an automatic recovery capture");
  await page.goto("./");
  await page.locator("#workspace > summary").click();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
  await page.locator("#file").setInputFiles(recovery);
  await expect(page.locator("#source")).toHaveText("Simulated bench");
  await expect(page.locator("#diagnosis .component-title")).toHaveText("I2C-1");
  await expect(page.locator("#diagnosis-state")).toHaveText("Resolved");
  await expect(page.locator("#recovery-attempts")).toBeVisible();
  await expect(page.locator("#recovery-history tbody tr")).toHaveCount(1);
  await expect(page.locator("#recovery-history")).toContainText("I2C bus clear");
  await expect(page.locator("#recovery-history")).toContainText("Verified");
  await page.getByRole("button", { name: "Restore fixture" }).click();
  await expect(page.locator("#recovery-attempts")).toBeHidden();
});
