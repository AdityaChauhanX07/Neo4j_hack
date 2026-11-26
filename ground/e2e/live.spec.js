import { expect, test } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

test("follow a real HTTP store through fault, recovery, connection loss, and disconnect", async ({ page }) => {
  test.skip(!process.env.RELATE_CLI, "requires the Relate HTTP server");
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const scratch = await mkdtemp(join(tmpdir(), "cc-browser-"));
  const store = join(scratch, "store");
  const writer = spawn(process.env.COMMONCAUSE_PYTHON || "python", ["-u", "ground/e2e/live-writer.py", store], {
    cwd: root, env: { ...process.env, PYTHONPATH: root }, stdio: ["pipe", "pipe", "pipe"],
  });
  const lines = createInterface({ input: writer.stdout })[Symbol.asyncIterator]();
  let writerLog = "";
  writer.stderr.on("data", chunk => { writerLog += chunk; });
  let server;
  let engineLog = "";
  async function phase(name) {
    writer.stdin.write(`${name}\n`);
    expect((await lines.next()).value, writerLog).toBe(name);
  }
  try {
    expect((await lines.next()).value, writerLog).toBe("ready");
    await phase("healthy");
    const socket = createServer();
    await new Promise(resolve => socket.listen(0, "127.0.0.1", resolve));
    const port = socket.address().port;
    await new Promise(resolve => socket.close(resolve));
    const origin = `http://127.0.0.1:${port}`;
    server = spawn(process.env.RELATE_CLI, ["serve", "--database", store, "--http", String(port), "--read-only=live"], {
      env: { ...process.env, RELATE_AUTH: "relate:live-browser-test" }, stdio: ["ignore", "ignore", "pipe"],
    });
    server.stderr.on("data", chunk => { engineLog += chunk; });
    await expect.poll(async () => {
      expect(server.exitCode, engineLog).toBeNull();
      try { return (await fetch(origin)).ok; } catch { return false; }
    }).toBe(true);
    await page.goto("./");
    await page.locator("#workspace > summary").click();
    await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
    await page.getByRole("button", { name: "Connect live", exact: true }).click();
    await page.getByLabel("Server origin").fill(origin);
    await page.getByLabel("User:token").fill("relate:wrong-token");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#notice")).toContainText("authentication required");
    await expect(page.locator("#source")).toHaveText("Synthetic fixture");
    await page.getByLabel("User:token").fill("relate:live-browser-test");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator("#source")).toHaveText("Live · Simulated bench");
    await expect(page.locator("#live-status")).toContainText("Connected");
    await expect(page.getByLabel("User:token")).toHaveValue("");
    await expect(page).not.toHaveURL(/live-browser-test/);
    await phase("fault");
    await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
    await expect(page.locator("#diagnosis-state")).toHaveText("Open");
    await page.selectOption("#part", "Bus:I2C-3");
    await page.locator(".console > summary").click();
    await page.fill("#query", "MATCH (n) DETACH DELETE n");
    await page.getByRole("button", { name: "Run query" }).click();
    await expect(page.locator("#query-status")).toContainText("READ transaction");
    await phase("recovered");
    await expect(page.locator("#diagnosis-state")).toHaveText("Resolved");
    await expect(page.locator("#part")).toHaveValue("Bus:I2C-3");
    server.kill();
    await new Promise(resolve => server.once("close", resolve));
    await expect(page.locator("#live-status")).toContainText("Connection interrupted");
    await expect(page.locator("#diagnosis .component-title")).toHaveText("REG_B");
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(page.locator("#source")).toHaveText("Synthetic fixture");
    await expect(page.getByRole("button", { name: "Disconnect", exact: true })).toBeDisabled();
  } finally {
    if (server && server.exitCode === null) {
      server.kill();
      await new Promise(resolve => server.once("close", resolve));
    }
    writer.stdin.end();
    if (writer.exitCode === null) await new Promise(resolve => writer.once("close", resolve));
    expect(writer.exitCode, writerLog).toBe(0);
    await rm(scratch, { recursive: true, force: true });
  }
});
