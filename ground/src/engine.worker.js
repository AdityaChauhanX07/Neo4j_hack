import init, { RelateDb } from "@relate/relate-wasm";
import wasmUrl from "@relate/relate-wasm/relate_bg.wasm?url";
import { loadSnapshot, querySnapshot } from "./graph-data.js";

let db;
self.onmessage = async ({ data }) => {
  const { id, snapshot, statement, parameters } = data;
  try {
    if (snapshot) {
      await init({ module_or_path: wasmUrl });
      db = new RelateDb();
      loadSnapshot(db, snapshot);
      self.postMessage({ id });
    } else {
      const result = querySnapshot(db, statement, parameters);
      const count = result.rows.length;
      self.postMessage({ id, result: { columns: result.columns, rows: result.rows.slice(0, 200), count } });
    }
  } catch (error) {
    self.postMessage({ id, error: error.message });
  }
};
