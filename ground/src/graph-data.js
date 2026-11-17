const identifier = /^[A-Za-z_][A-Za-z0-9_]*$/;
const importLabel = "_DownlinkNode";
const importKey = "__downlink_id";

const readOperators = new Set([
  "AllNodesScan", "AllRelationshipsScan", "Apply", "Argument", "CartesianProduct",
  "Distinct", "EagerAggregation", "Expand", "Filter", "HashJoin", "Limit",
  "NodeByLabelScan", "NodeByIdSeek", "NodeIndexScan", "NodeIndexSeek",
  "Optional", "Optional(Expand)", "ProduceResults", "Projection",
  "RelationshipByIdSeek", "RelationshipByTypeScan", "SemiApply", "Skip", "Sort",
  "Top", "Union", "UnionAll", "Unwind", "VarLengthExpand",
]);

function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function validateSnapshot(snapshot) {
  if (!object(snapshot) || !Array.isArray(snapshot.nodes) || !Array.isArray(snapshot.rels)) {
    throw new Error("Expected a downlink JSON file with nodes and rels.");
  }

  const ids = new Set();
  for (const node of snapshot.nodes) {
    if (!object(node) || typeof node.id !== "string" || !node.id || ids.has(node.id)
      || typeof node.label !== "string" || !identifier.test(node.label)
      || node.label === importLabel || !object(node.props) || Object.hasOwn(node.props, importKey)) {
      throw new Error("The downlink contains an invalid node or duplicate ID.");
    }
    ids.add(node.id);
  }
  for (const rel of snapshot.rels) {
    if (!object(rel) || typeof rel.type !== "string" || !identifier.test(rel.type)
      || !ids.has(rel.from) || !ids.has(rel.to) || !object(rel.props)) {
      throw new Error("The downlink contains an invalid relationship or a missing endpoint.");
    }
  }
}

function groups(items, key) {
  const grouped = new Map();
  for (const item of items) {
    const name = item[key];
    if (!grouped.has(name)) grouped.set(name, []);
    grouped.get(name).push(item);
  }
  return grouped;
}

function execute(db, statement, parameters = {}) {
  const result = JSON.parse(db.execute(statement, JSON.stringify(parameters)));
  if (result.error) throw new Error(result.error);
  return result;
}

export function loadSnapshot(db, snapshot) {
  validateSnapshot(snapshot);
  execute(db, `CREATE CONSTRAINT cc_import FOR (n:${importLabel}) REQUIRE n.${importKey} IS UNIQUE`);
  for (const [label, rows] of groups(snapshot.nodes, "label")) {
    execute(db, `
      UNWIND $rows AS row
      CREATE (n:${label}:${importLabel})
      SET n += row.props, n.${importKey} = row.id
    `, { rows });
  }
  for (const [type, rows] of groups(snapshot.rels, "type")) {
    execute(db, `
      UNWIND $rows AS row
      MATCH (a:${importLabel} {${importKey}: row.from}), (b:${importLabel} {${importKey}: row.to})
      CREATE (a)-[r:${type}]->(b)
      SET r += row.props
    `, { rows });
  }
  execute(db, "DROP CONSTRAINT cc_import");
  execute(db, `MATCH (n:${importLabel}) REMOVE n.${importKey}, n:${importLabel}`);
}

function readPlan(operator) {
  if (operator.operator === "Catalog") {
    return ["SHOW CONSTRAINTS", "SHOW INDEXES"].includes(operator.details);
  }
  if (operator.operator === "ProcedureCall") {
    return ["db.labels()", "db.propertyKeys()", "db.relationshipTypes()"].includes(operator.details);
  }
  return readOperators.has(operator.operator) && operator.children.every(readPlan);
}

export function querySnapshot(db, statement, parameters = {}) {
  if (!statement.trim()) throw new Error("Enter a Cypher query.");
  if (!object(parameters)) throw new Error("Query parameters must be a JSON object.");
  const { plan } = execute(db, `EXPLAIN ${statement}`, parameters);
  if (!plan?.root || !readPlan(plan.root)) {
    throw new Error("The console accepts graph reads. Writes, external loads, and unverified operators are disabled.");
  }
  return execute(db, statement, parameters);
}
