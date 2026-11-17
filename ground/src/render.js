export function element(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined && value !== null) node.textContent = value;
  if (className) node.className = className;
  return node;
}

export function options(select, choices, value) {
  const nodes = choices.map(choice => new Option(choice.label, choice.id));
  select.replaceChildren(...nodes);
  if (value !== undefined) select.value = value;
}

export function table(container, columns, rows, makeCell, emptyMessage = "No rows", rowClass) {
  if (!rows.length) {
    container.replaceChildren(element("p", emptyMessage, "empty"));
    return;
  }
  const output = element("table");
  const head = output.createTHead().insertRow();
  for (const { label } of columns) {
    const cell = element("th", label);
    cell.scope = "col";
    head.append(cell);
  }
  const body = output.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    if (rowClass) tr.className = rowClass(row);
    for (const { key } of columns) {
      const cell = tr.insertCell();
      if (makeCell) makeCell(cell, key, row);
      else cell.textContent = show(row[key]);
    }
  }
  container.replaceChildren(output);
}

export function show(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function metering(label, value) {
  const metric = element("div", null, "metric");
  metric.append(element("strong", value), element("span", label));
  return metric;
}

export function showDiagnosis(container, suspects, procedures, episode) {
  if (!suspects.length) {
    container.replaceChildren(element("p", "No diagnosis in this downlink.", "empty"));
    return;
  }
  const first = suspects[0];
  const metrics = element("div", null, "metrics");
  metrics.append(
    metering("Score", Number(first.score).toFixed(2)),
    metering("Covered", first.covered),
    metering("Contradicted", first.contradicted),
  );
  container.replaceChildren(
    element("p", first.suspect, "component-title"),
    element("p", `${first.kind} · ${episode.confidence} confidence`, "component-kind"),
    metrics,
  );

  if (suspects.length > 1) {
    const ranks = element("div", null, "rank-table table-scroll");
    table(ranks, [
      { key: "suspect", label: "Ranked part" }, { key: "score", label: "Score" },
      { key: "covered", label: "Covered" }, { key: "contradicted", label: "Against" },
    ], suspects, (cell, key, row) => {
      cell.textContent = key === "score" ? Number(row.score).toFixed(2) : show(row[key]);
    });
    container.append(ranks);
  }

  for (const procedure of procedures) {
    const section = element("section", null, "recovery");
    const caption = suspects.length > 1 ? `${procedure.suspect} · ${procedure.procedure}` : procedure.procedure;
    section.append(element("h3", caption), element("p", procedure.failure_mode));
    if (Array.isArray(procedure.steps)) {
      const steps = element("ol");
      for (const step of procedure.steps) steps.append(element("li", step));
      section.append(steps);
    }
    container.append(section);
  }
}
