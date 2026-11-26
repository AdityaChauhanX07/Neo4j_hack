export function openHttpEngine(address, credential, { fetcher = fetch } = {}) {
  const origin = new URL(address);
  if (!["http:", "https:"].includes(origin.protocol) || origin.username || origin.password
    || origin.pathname !== "/" || origin.search || origin.hash) {
    throw new Error("Enter the server origin, for example http://127.0.0.1:7474.");
  }
  if (!credential.includes(":")) throw new Error("Enter the server's user:token credential.");
  const bytes = new TextEncoder().encode(credential);
  const authorization = `Basic ${btoa(String.fromCharCode(...bytes))}`;
  const endpoint = new URL("db/neo4j/query/v2/tx", origin);
  const pending = new Set();
  let closed = false;

  async function request(url, payload, signal) {
    const response = await fetcher(url, {
      method: "POST", signal, cache: "no-store", credentials: "omit", redirect: "error",
      headers: { "Content-Type": "application/json", Accept: "application/json", Authorization: authorization },
      body: JSON.stringify(payload),
    });
    const envelope = await response.json();
    if (!response.ok || envelope.errors?.length) {
      throw new Error(envelope.errors?.map(error => error.message).join("; ") || `Relate returned HTTP ${response.status}.`);
    }
    return envelope;
  }

  async function query(statement, parameters = {}) {
    if (closed) throw new Error("The live connection is closed.");
    if (!statement.trim()) throw new Error("Enter a Cypher query.");
    if (!parameters || typeof parameters !== "object" || Array.isArray(parameters)) {
      throw new Error("Query parameters must be a JSON object.");
    }
    const controller = new AbortController();
    pending.add(controller);
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      // accessMode is enforced on managed transactions, but ignored on auto-commit requests.
      const envelope = await request(endpoint, { statement, parameters, accessMode: "READ" }, controller.signal);
      const transaction = envelope.transaction?.id;
      if (!transaction) throw new Error("The server did not open a read transaction.");
      await request(`${endpoint}/${encodeURIComponent(transaction)}/commit`, {}, controller.signal);
      const { fields, values } = envelope.data;
      return {
        columns: fields, count: values.length,
        rows: values.slice(0, 200).map(row => Object.fromEntries(fields.map((name, index) => [name, row[index]]))),
      };
    } finally {
      clearTimeout(timer);
      pending.delete(controller);
    }
  }

  async function snapshot() {
    const nodes = await query(`
      MATCH (n) WHERE NOT n:Event AND NOT n:Diagnosis
      RETURN elementId(n) AS key, labels(n)[0] AS label, properties(n) AS props
    `);
    if (nodes.count > nodes.rows.length) throw new Error("The live topology exceeds the 200-node view limit.");
    const keys = new Map(nodes.rows.map(row => [row.key, `${row.label}:${row.props.id ?? row.props.code}`]));
    const links = await query(`
      MATCH (a)-[r]->(b)
      WHERE NOT a:Event AND NOT a:Diagnosis AND NOT b:Event AND NOT b:Diagnosis
      RETURN type(r) AS type, elementId(a) AS source, elementId(b) AS target, properties(r) AS props
    `);
    if (links.count > links.rows.length) throw new Error("The live topology exceeds the 200-relationship view limit.");
    return {
      nodes: nodes.rows.map(row => ({ id: keys.get(row.key), label: row.label, props: row.props })),
      rels: links.rows.map(row => ({ type: row.type, from: keys.get(row.source), to: keys.get(row.target), props: row.props })),
    };
  }

  return {
    query, snapshot,
    close() {
      closed = true;
      for (const controller of pending) controller.abort();
      pending.clear();
    },
  };
}
