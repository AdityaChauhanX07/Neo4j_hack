import { readFile, writeFile } from "node:fs/promises";
import { openHttpEngine } from "../ground/src/http-engine.js";

const [address, report] = process.argv.slice(2);
const engine = openHttpEngine(address, process.env.RELATE_AUTH);
const impact = await readFile(new URL("../queries/impact.cypher", import.meta.url), "utf8");
const started = performance.now();
let stopped = false;
let polls = 0;
let failed = 0;
process.on("SIGTERM", () => { stopped = true; });
process.on("SIGINT", () => { stopped = true; });

try {
  await engine.snapshot();
  while (!stopped) {
    try {
      const [episodes] = await Promise.all([
        engine.query(`MATCH (dx:Diagnosis)
          RETURN dx.id AS id, dx.run AS run, dx.state AS state, dx.confidence AS confidence,
                 dx.window_from AS start, dx.window_to AS end ORDER BY dx.ts DESC, dx.id DESC`),
        engine.query("MATCH (r:Run) RETURN r.id AS id, properties(r) AS props"),
        engine.query("MATCH (e:Event) RETURN max(e.ts) AS last"),
      ]);
      if (episodes.rows.length) throw new Error("The healthy workload opened a diagnosis");
      await engine.query(impact, { part: "drv.imu" });
      polls += 1;
    } catch (error) {
      failed += 1;
      console.error(error.message);
    }
    if (!stopped) await new Promise(resolve => setTimeout(resolve, 1000));
  }
} finally {
  engine.close();
  const usage = process.resourceUsage();
  await writeFile(report, JSON.stringify({
    polls, failed, elapsed_seconds: (performance.now() - started) / 1000,
    cpu_seconds: (usage.userCPUTime + usage.systemCPUTime) / 1e6,
    peak_rss_bytes: usage.maxRSS * 1024,
  }, null, 2) + "\n");
}
