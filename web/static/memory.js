// Memory browser/editor page. Data-driven: one config object per record
// type drives the list columns, the add/update form fields, and which API
// endpoints to call — see api/routes.py for the corresponding backend
// (TABLE_MAP there uses the same URL segment names as the keys below).

const RECORD_TYPES = {
  people: {
    label: "People",
    columns: ["id", "name", "relation_context", "notes", "last_mentioned_at"],
    searchable: true,
    fields: [
      { name: "id", label: "ID (unique, e.g. 'sarah')", type: "text", required: true },
      { name: "name", label: "Name", type: "text", required: true },
      { name: "relation_context", label: "Relation to user", type: "text" },
      { name: "notes", label: "Notes", type: "textarea" },
      { name: "last_mentioned_at", label: "Last mentioned (turn #)", type: "number", default: 0 },
    ],
  },
  relationships: {
    label: "Relationships",
    columns: ["id", "party_a", "party_b", "relation_type", "polarity", "valid_from_turn"],
    searchable: true,
    fields: [
      { name: "id", label: "ID", type: "text", required: true },
      { name: "party_a", label: "Party A (person id or 'user')", type: "text", required: true },
      { name: "party_b", label: "Party B (person id or 'user')", type: "text", required: true },
      { name: "relation_type", label: "Relation type", type: "text" },
      { name: "polarity", label: "Polarity (-1.0 to 1.0)", type: "number", step: "0.1", default: 0 },
      { name: "valid_from_turn", label: "Valid from turn", type: "number", default: 0 },
    ],
  },
  "standing-facts": {
    label: "Standing Facts",
    columns: ["id", "subject_id", "fact", "category", "sensitive", "valid_from_turn"],
    searchable: true,
    fields: [
      { name: "id", label: "ID", type: "text", required: true },
      { name: "subject_id", label: "Subject ('user' or person id)", type: "text", default: "user" },
      { name: "fact", label: "Fact", type: "textarea", required: true },
      { name: "category", label: "Category", type: "text" },
      { name: "sensitive", label: "Sensitive", type: "checkbox" },
      { name: "valid_from_turn", label: "Valid from turn", type: "number", default: 0 },
      { name: "valid_to_turn", label: "Valid to turn (optional)", type: "number" },
    ],
  },
  "episodic-events": {
    label: "Episodic Events",
    columns: ["id", "summary", "participants", "occurred_at", "category", "sentiment", "sensitive", "consolidated"],
    searchable: true,
    fields: [
      { name: "id", label: "ID", type: "text", required: true },
      { name: "summary", label: "Summary", type: "textarea", required: true },
      { name: "participants", label: "Participants (comma-separated person ids)", type: "list" },
      { name: "occurred_at", label: "Occurred at (free text)", type: "text" },
      { name: "category", label: "Category (emotional/practical/factual/other)", type: "text" },
      { name: "sentiment", label: "Sentiment (-1.0 to 1.0)", type: "number", step: "0.1" },
      { name: "sensitive", label: "Sensitive", type: "checkbox" },
      { name: "session_id", label: "Session ID", type: "text" },
    ],
  },
  commitments: {
    label: "Commitments",
    columns: ["id", "description", "concerns", "status", "sensitive", "resolution_note"],
    searchable: true,
    fields: [
      { name: "id", label: "ID", type: "text", required: true },
      { name: "description", label: "Description", type: "textarea", required: true },
      { name: "concerns", label: "Concerns (comma-separated person ids)", type: "list" },
      { name: "status", label: "Status", type: "select", options: ["open", "completed", "dropped", "deferred"], default: "open" },
      { name: "sensitive", label: "Sensitive", type: "checkbox" },
      { name: "resolution_note", label: "Resolution note", type: "text" },
    ],
  },
  "user-profile": {
    label: "User Profile",
    columns: ["id", "name", "timezone", "communication_prefs"],
    searchable: false,
    fields: [
      { name: "id", label: "ID", type: "text", default: "user", required: true },
      { name: "name", label: "Name", type: "text" },
      { name: "timezone", label: "Timezone", type: "text" },
      { name: "communication_prefs", label: "Communication preferences (comma-separated)", type: "list" },
    ],
  },
};

const tabsEl = document.getElementById("tabs");
const listTitleEl = document.getElementById("list-title");
const listContainerEl = document.getElementById("list-container");
const formContainerEl = document.getElementById("form-container");
const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const clearSearchBtn = document.getElementById("clear-search-btn");

let activeType = Object.keys(RECORD_TYPES)[0];

function apiUrl(path) {
  return `/api${path}`;
}

function renderTabs() {
  tabsEl.innerHTML = "";
  for (const [key, config] of Object.entries(RECORD_TYPES)) {
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (key === activeType ? " active" : "");
    btn.textContent = config.label;
    btn.addEventListener("click", () => {
      activeType = key;
      searchInput.value = "";
      renderTabs();
      renderForm();
      loadList();
    });
    tabsEl.appendChild(btn);
  }
}

function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function renderTable(records) {
  const config = RECORD_TYPES[activeType];
  listTitleEl.textContent = `${config.label} (${records.length})`;

  if (!records.length) {
    listContainerEl.innerHTML = '<div class="empty-state">No records yet.</div>';
    return;
  }

  const table = document.createElement("table");
  table.className = "record-table";
  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>${config.columns.map((c) => `<th>${c}</th>`).join("")}</tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const record of records) {
    const tr = document.createElement("tr");
    tr.innerHTML = config.columns
      .map((c) => {
        const raw = formatCell(record[c]);
        const badge = c === "sensitive" && record[c] ? ' <span class="badge">sensitive</span>' : "";
        return `<td>${escapeHtml(raw)}${badge}</td>`;
      })
      .join("");
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);

  listContainerEl.innerHTML = "";
  listContainerEl.appendChild(table);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadList() {
  listContainerEl.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const resp = await fetch(apiUrl(`/memory/${activeType}`));
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    const records = await resp.json();
    renderTable(records);
  } catch (err) {
    console.error(err);
    listContainerEl.innerHTML = `<div class="empty-state">Failed to load: ${escapeHtml(err.message)}</div>`;
  }
}

async function runSearch() {
  const config = RECORD_TYPES[activeType];
  const q = searchInput.value.trim();
  if (!config.searchable || !q) {
    loadList();
    return;
  }
  listContainerEl.innerHTML = '<div class="empty-state">Searching…</div>';
  try {
    const resp = await fetch(apiUrl(`/memory/search/${activeType}?q=${encodeURIComponent(q)}&limit=15`));
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    const records = await resp.json();
    renderTable(records);
  } catch (err) {
    console.error(err);
    listContainerEl.innerHTML = `<div class="empty-state">Search failed: ${escapeHtml(err.message)}</div>`;
  }
}

searchBtn.addEventListener("click", runSearch);
clearSearchBtn.addEventListener("click", () => {
  searchInput.value = "";
  loadList();
});
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    runSearch();
  }
});

function renderForm() {
  const config = RECORD_TYPES[activeType];
  const form = document.createElement("form");
  form.className = "form-grid";

  for (const field of config.fields) {
    const label = document.createElement("label");
    if (field.type === "textarea" || field.type === "text" || field.name === "description" || field.name === "fact" || field.name === "summary") {
      label.className = field.type === "textarea" ? "full-width" : "";
    }
    let input;
    if (field.type === "textarea") {
      input = document.createElement("textarea");
      input.rows = 3;
      label.className = "full-width";
    } else if (field.type === "select") {
      input = document.createElement("select");
      for (const opt of field.options) {
        const optionEl = document.createElement("option");
        optionEl.value = opt;
        optionEl.textContent = opt;
        input.appendChild(optionEl);
      }
    } else if (field.type === "checkbox") {
      input = document.createElement("input");
      input.type = "checkbox";
    } else {
      input = document.createElement("input");
      input.type = field.type === "list" ? "text" : field.type;
      if (field.step) input.step = field.step;
    }
    input.name = field.name;
    if (field.default !== undefined && field.type !== "checkbox") input.value = field.default;
    if (field.default !== undefined && field.type === "checkbox") input.checked = !!field.default;
    if (field.required) input.required = true;

    label.prepend(input);
    const labelText = document.createElement("span");
    labelText.textContent = field.label;
    label.prepend(labelText);
    form.appendChild(label);
  }

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = `Save to ${config.label}`;
  form.appendChild(submitBtn);

  const statusEl = document.createElement("div");
  statusEl.className = "empty-state";
  form.appendChild(statusEl);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = buildPayload(config, form);
    statusEl.textContent = "Saving…";
    try {
      const resp = await fetch(apiUrl(`/memory/${activeType}`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
      statusEl.textContent = "Saved.";
      form.reset();
      loadList();
    } catch (err) {
      console.error(err);
      statusEl.textContent = `Failed: ${err.message}`;
    }
  });

  formContainerEl.innerHTML = "";
  formContainerEl.appendChild(form);
}

function buildPayload(config, form) {
  const data = new FormData(form);
  const payload = {};
  for (const field of config.fields) {
    if (field.type === "checkbox") {
      payload[field.name] = form.elements[field.name].checked;
      continue;
    }
    const raw = data.get(field.name);
    if (raw === null || raw === "") continue; // let backend defaults apply
    if (field.type === "number") {
      payload[field.name] = parseFloat(raw);
    } else if (field.type === "list") {
      payload[field.name] = raw.split(",").map((s) => s.trim()).filter(Boolean);
    } else {
      payload[field.name] = raw;
    }
  }
  return payload;
}

renderTabs();
renderForm();
loadList();
