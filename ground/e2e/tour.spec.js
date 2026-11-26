import { expect, test } from "@playwright/test";

test("a first visitor can follow the fault and recovery before opening technical tools", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "Three alarms. One shared cause." })).toBeVisible();
  await expect(page.locator("#workspace")).not.toHaveAttribute("open", "");
  await expect(page.locator("#wiring canvas")).toHaveCount(0);
  await expect(page.locator("#tour-title")).toHaveText("Start with a healthy system.");
  await page.getByRole("button", { name: "Try a fault", exact: true }).click();
  await page.getByRole("button", { name: "Introduce the fault", exact: true }).click();
  await expect(page.locator("#tour-title")).toHaveText("3 devices need attention.");
  await expect(page.locator("#tour-description")).toContainText("Motion sensor");
  await expect(page.locator("#tour-map")).toHaveAttribute("data-stage", "1");
  await page.getByRole("button", { name: "See the diagnosis", exact: true }).click();
  await expect(page.locator("#tour-title")).toHaveText("Regulator B");
  await expect(page.locator("#tour-proof")).toContainText("still responding");
  await expect(page.locator("#tour-map svg path")).toHaveCount(3);
  await page.getByRole("button", { name: "Check the recovery", exact: true }).click();
  await expect(page.locator("#tour-title")).toHaveText("The readings return.");
  await expect(page.locator("#tour-map-state")).toHaveText("Recovery recorded");
  await page.getByRole("button", { name: "Show me the recorded evidence" }).click();
  await expect(page.locator("#workspace")).toHaveAttribute("open", "");
  await expect(page.locator("#wiring canvas").first()).toBeVisible();
  await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
});

test("switch faults and systems without presenting uncertain results as high confidence", async ({ page }) => {
  await page.goto("./");
  await expect(page.locator("#tour-title")).toHaveText("Start with a healthy system.");
  await page.getByRole("button", { name: /Two faults at once/ }).click();
  await page.locator('[data-stage="2"]').click();
  await expect(page.locator("#tour-title")).toContainText("Regulator B and Data bus 3");
  await expect(page.locator("#tour-proof")).toContainText("More inspection needed");
  await expect(page.locator("#tour-map .map-root")).toHaveCount(2);
  await page.getByRole("button", { name: /Try the same idea on a drone/ }).click();
  await expect(page.locator("#tour-system")).toContainText("Quadcopter");
  await expect(page.locator("#tour-title")).toHaveText("Start with a healthy system.");
  await page.locator('[data-stage="2"]').click();
  await expect(page.locator("#tour-title")).toHaveText("5 V regulator");
});

test("the mobile walkthrough stays readable and keyboard steps expose the current stage", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await expect(page.locator("#tour-title")).toHaveText("Start with a healthy system.");
  await page.locator('[data-stage="1"]').focus();
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-stage="1"]')).toHaveAttribute("aria-current", "step");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.screenshot({ path: info.outputPath("guided-mobile.png"), fullPage: true });
});
