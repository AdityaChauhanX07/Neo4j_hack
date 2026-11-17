export function openEngine(snapshot) {
  const worker = new Worker(new URL("./engine.worker.js", import.meta.url), { type: "module" });
  const pending = new Map();
  let sequence = 0;
  let closed = false;

  function close(message = "The downlink was closed.") {
    closed = true;
    worker.terminate();
    for (const { reject, timer } of pending.values()) {
      clearTimeout(timer);
      reject(new Error(message));
    }
    pending.clear();
  }

  worker.onmessage = ({ data }) => {
    const request = pending.get(data.id);
    if (!request) return;
    pending.delete(data.id);
    clearTimeout(request.timer);
    if (data.error) request.reject(new Error(data.error));
    else request.resolve(data.result);
  };
  worker.onerror = () => close("The Relate worker stopped. Reopen the downlink to retry.");

  function request(payload) {
    if (closed) return Promise.reject(new Error("Reopen the downlink to retry."));
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => close("Relate timed out. Reopen the downlink or use a smaller query."), 15000);
      pending.set(id, { resolve, reject, timer });
      worker.postMessage({ id, ...payload });
    });
  }

  return {
    ready: request({ snapshot }),
    query: (statement, parameters) => request({ statement, parameters }),
    close,
  };
}
