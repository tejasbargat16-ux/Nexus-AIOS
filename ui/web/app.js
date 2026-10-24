/**
 * NEXUS AIOS - WEB CONSOLE APPLICATION
 * Client-side Controller for API, Intent Planning, Tools, and Memory.
 */

const API_BASE = ""; // Relative to host
let currentTools = [];

// =============================================================================
// Initialization & Tab Navigation
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initChat();
  initTools();
  initMemory();
  initAudit();
  
  // Start background status poll
  pollStatus();
  setInterval(pollStatus, 4000);
});

function initTabs() {
  const tabs = document.querySelectorAll(".nav-tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");

      const target = tab.dataset.tab;
      document.querySelectorAll(".tab-pane").forEach((pane) => {
        pane.classList.remove("active");
      });
      const activePane = document.getElementById(`pane-${target}`);
      if (activePane) activePane.classList.add("active");

      // Load tab-specific data on activation
      if (target === "tools") loadToolsCatalog();
      if (target === "memory") loadMemoryFacts();
      if (target === "audit") loadAuditStream();
    });
  });
}

// =============================================================================
// Status Polling
// =============================================================================

async function pollStatus() {
  try {
    const res = await fetch(`${API_BASE}/status`);
    if (!res.ok) throw new Error("Offline");
    const data = await res.json();

    // Update Status Pill
    const pillText = document.getElementById("daemon-status-text");
    pillText.textContent = "Kernel Active";

    // Update Provider
    const provName = document.getElementById("provider-name");
    const prov = data.providers?.preferred || "cloud";
    const cloud = data.providers?.cloud;
    const modelTag = cloud?.configured ? cloud.model : "offline";
    provName.textContent = `${prov.toUpperCase()}: ${modelTag}`;

    // Update Uptime
    const uptimeEl = document.getElementById("uptime-text");
    if (data.uptime_seconds !== undefined) {
      uptimeEl.textContent = `${Math.round(data.uptime_seconds)}s`;
    }

    // Update Badges
    const toolsBadge = document.getElementById("tools-count-badge");
    if (data.components?.tools_registered) {
      toolsBadge.textContent = data.components.tools_registered;
    }
    const factsBadge = document.getElementById("facts-count-badge");
    if (data.components?.stored_facts !== undefined) {
      factsBadge.textContent = data.components.stored_facts;
    }
  } catch (err) {
    const pillText = document.getElementById("daemon-status-text");
    pillText.textContent = "Reconnecting...";
  }
}

// =============================================================================
// 1. Chat & Intent Console
// =============================================================================

function initChat() {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("intent-input");

  // Prompt chip click handlers
  document.querySelectorAll(".prompt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      input.value = chip.dataset.prompt;
      form.dispatchEvent(new Event("submit"));
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    const prefer = document.getElementById("route-selector").value;
    input.value = "";

    // Append User Message
    appendMessage("user", text);

    // Append Loading State
    const loadingId = appendLoading();

    try {
      await sendIntentRequest(text, prefer, false, loadingId);
    } catch (err) {
      removeMessage(loadingId);
      appendMessage("ai", `Error executing intent: ${err.message}`, { error: true });
    }
  });
}

async function sendIntentRequest(text, prefer, confirmed, loadingId) {
  const res = await fetch(`${API_BASE}/intent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, prefer, confirmed }),
  });

  const data = await res.json();
  removeMessage(loadingId);

  // 1. Handle Security Confirmation Required
  if (data.status === "confirmation_required") {
    appendConfirmationCard(data, text, prefer);
    return;
  }

  // 2. Render Standard AI Response & Tool Results
  appendMessage("ai", data.reply || "Done.", {
    provider: data.provider,
    duration_ms: data.duration_ms,
    tool_result: data.tool_result,
  });
}

function appendMessage(role, text, meta = {}) {
  const container = document.getElementById("chat-messages");
  const card = document.createElement("div");
  card.className = `message-card ${role}`;

  let metaHtml = "";
  if (role === "ai" && meta.provider) {
    metaHtml = `
      <div class="message-meta">
        <span class="meta-provider">[${meta.provider}]</span>
        ${meta.duration_ms ? `<span class="meta-duration">${meta.duration_ms}ms</span>` : ""}
      </div>
    `;
  }

  let toolHtml = "";
  if (meta.tool_result) {
    toolHtml = `
      <div class="tool-result-box">
        <div class="tool-header-tag">
          <span>⚡ Tool Executed</span>
          <span>${meta.tool_result.status || "ok"}</span>
        </div>
        <pre>${escapeHtml(JSON.stringify(meta.tool_result, null, 2))}</pre>
      </div>
    `;
  }

  card.innerHTML = `
    ${metaHtml}
    <div class="message-body">${escapeHtml(text)}</div>
    ${toolHtml}
  `;

  container.appendChild(card);
  container.scrollTop = container.scrollHeight;
  return card;
}

function appendConfirmationCard(data, originalText, prefer) {
  const container = document.getElementById("chat-messages");
  const card = document.createElement("div");
  card.className = "message-card ai";

  card.innerHTML = `
    <div class="security-confirm-card">
      <div class="confirm-title">
        <span>⚠️ Security Guard Authorization Required</span>
      </div>
      <p>The AI planned to execute action <strong>${escapeHtml(data.action)}</strong> with parameters:</p>
      <pre style="margin: 8px 0; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 4px; font-size: 0.8rem;">${escapeHtml(JSON.stringify(data.params, null, 2))}</pre>
      <div class="confirm-actions">
        <button class="btn-approve" id="approve-btn">Approve & Execute</button>
        <button class="btn-decline" id="decline-btn">Decline</button>
      </div>
    </div>
  `;

  container.appendChild(card);
  container.scrollTop = container.scrollHeight;

  card.querySelector("#approve-btn").addEventListener("click", async () => {
    card.remove();
    const loadingId = appendLoading();
    await sendIntentRequest(originalText, prefer, true, loadingId);
  });

  card.querySelector("#decline-btn").addEventListener("click", () => {
    card.remove();
    appendMessage("ai", `Action '${data.action}' was declined by user.`, { provider: "guard" });
  });
}

function appendLoading() {
  const container = document.getElementById("chat-messages");
  const id = `loading-${Date.now()}`;
  const card = document.createElement("div");
  card.id = id;
  card.className = "message-card ai";
  card.innerHTML = `
    <div class="message-meta"><span class="meta-provider">Processing Intent...</span></div>
    <div class="pulse-dot" style="display: inline-block;"></div> Thinking...
  `;
  container.appendChild(card);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeMessage(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// =============================================================================
// 2. Tools Catalog & Direct Execution
// =============================================================================

function initTools() {
  loadToolsCatalog();

  document.getElementById("tool-search").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = currentTools.filter((t) =>
      t.action.toLowerCase().includes(q) || t.description.toLowerCase().includes(q)
    );
    renderToolsGrid(filtered);
  });

  // Modal handlers
  document.getElementById("close-tool-modal").addEventListener("click", closeToolModal);
  document.getElementById("modal-cancel-btn").addEventListener("click", closeToolModal);
}

async function loadToolsCatalog() {
  try {
    const res = await fetch(`${API_BASE}/tools`);
    const data = await res.json();
    currentTools = data.tools || [];
    renderToolsGrid(currentTools);
  } catch (err) {
    console.error("Failed to load tools", err);
  }
}

function renderToolsGrid(tools) {
  const grid = document.getElementById("tools-grid");
  grid.innerHTML = "";

  tools.forEach((tool) => {
    const card = document.createElement("div");
    card.className = "tool-card";
    const category = tool.action.split(".")[0];

    card.innerHTML = `
      <div>
        <div class="tool-card-title">
          <span class="tool-action-tag">${escapeHtml(tool.action)}</span>
        </div>
        <p class="tool-desc">${escapeHtml(tool.description)}</p>
      </div>
      <div class="tool-card-footer">
        <span class="tool-category-badge">${category}</span>
        <span style="font-size: 0.8rem; color: var(--accent-cyan); font-weight: 500;">Run Tool ↗</span>
      </div>
    `;

    card.addEventListener("click", () => openToolModal(tool));
    grid.appendChild(card);
  });
}

function openToolModal(tool) {
  document.getElementById("modal-tool-name").textContent = tool.action;
  document.getElementById("modal-tool-desc").textContent = tool.description;
  const container = document.getElementById("modal-params-container");
  container.innerHTML = "";

  // Render parameter input fields
  const params = tool.parameters || {};
  Object.keys(params).forEach((paramName) => {
    const typeHint = params[paramName];
    const group = document.createElement("div");
    group.className = "form-group";
    group.innerHTML = `
      <label>${paramName} <span style="color: var(--text-dim);">(${typeHint})</span></label>
      <input type="text" data-param="${paramName}" placeholder="Enter ${paramName}..." />
    `;
    container.appendChild(group);
  });

  const outputBox = document.getElementById("modal-tool-output");
  outputBox.textContent = "Awaiting execution...";

  const runBtn = document.getElementById("modal-run-btn");
  runBtn.onclick = async () => {
    const collectedParams = {};
    container.querySelectorAll("input").forEach((inp) => {
      const val = inp.value.trim();
      if (val) collectedParams[inp.dataset.param] = val;
    });

    outputBox.textContent = "Executing...";
    try {
      const res = await fetch(`${API_BASE}/tool/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: tool.action, params: collectedParams, confirmed: true }),
      });
      const data = await res.json();
      outputBox.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
      outputBox.textContent = `Error: ${err.message}`;
    }
  };

  document.getElementById("tool-exec-modal").classList.add("open");
}

function closeToolModal() {
  document.getElementById("tool-exec-modal").classList.remove("open");
}

// =============================================================================
// 3. Memory & Facts
// =============================================================================

function initMemory() {
  const modal = document.getElementById("add-fact-modal");
  document.getElementById("open-add-fact-modal").addEventListener("click", () => {
    modal.classList.add("open");
  });
  document.getElementById("close-fact-modal").addEventListener("click", () => {
    modal.classList.remove("open");
  });
  document.getElementById("cancel-fact-btn").addEventListener("click", () => {
    modal.classList.remove("open");
  });

  document.getElementById("add-fact-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = document.getElementById("fact-key").value.trim();
    const value = document.getElementById("fact-value").value.trim();
    const category = document.getElementById("fact-category").value.trim() || "general";

    if (!key || !value) return;

    await fetch(`${API_BASE}/memory/facts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value, category }),
    });

    modal.classList.remove("open");
    document.getElementById("add-fact-form").reset();
    loadMemoryFacts();
  });

  document.getElementById("memory-search-btn").addEventListener("click", async () => {
    const q = document.getElementById("memory-search-input").value.trim();
    if (!q) {
      loadMemoryFacts();
      return;
    }
    const res = await fetch(`${API_BASE}/memory/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    renderSearchResults(data.results || []);
  });
}

async function loadMemoryFacts() {
  try {
    const res = await fetch(`${API_BASE}/memory/facts`);
    const data = await res.json();
    renderFactsList(data.facts || []);
  } catch (err) {
    console.error("Failed to load facts", err);
  }
}

function renderFactsList(facts) {
  const list = document.getElementById("facts-list");
  list.innerHTML = "";

  if (facts.length === 0) {
    list.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 32px;">No memory facts recorded yet.</div>`;
    return;
  }

  facts.forEach((fact) => {
    const item = document.createElement("div");
    item.className = "fact-item";
    item.innerHTML = `
      <div>
        <div class="fact-key">${escapeHtml(fact.key)}</div>
        <div class="fact-value">${escapeHtml(JSON.stringify(fact.value))}</div>
      </div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <span class="fact-cat-tag">${escapeHtml(fact.category || "general")}</span>
        <button class="btn-decline" style="padding: 4px 8px; font-size: 0.75rem;" title="Delete Fact">✕</button>
      </div>
    `;

    item.querySelector("button").addEventListener("click", async () => {
      await fetch(`${API_BASE}/memory/facts/${encodeURIComponent(fact.key)}`, { method: "DELETE" });
      loadMemoryFacts();
    });

    list.appendChild(item);
  });
}

function renderSearchResults(results) {
  const list = document.getElementById("facts-list");
  list.innerHTML = "";

  if (results.length === 0) {
    list.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 32px;">No matches found for search query.</div>`;
    return;
  }

  results.forEach((r) => {
    const item = document.createElement("div");
    item.className = "fact-item";
    item.innerHTML = `
      <div>
        <div class="fact-key">${escapeHtml(r.key || `Memory #${r.id}`)}</div>
        <div class="fact-value">${escapeHtml(JSON.stringify(r.content))}</div>
      </div>
      <div>
        <span class="meta-duration">Score: ${r.score}</span>
      </div>
    `;
    list.appendChild(item);
  });
}

// =============================================================================
// 4. Audit & Security Stream
// =============================================================================

function initAudit() {
  document.getElementById("refresh-audit-btn").addEventListener("click", loadAuditStream);
}

async function loadAuditStream() {
  try {
    const res = await fetch(`${API_BASE}/audit?limit=40`);
    const data = await res.json();
    renderAuditStream(data.entries || []);
  } catch (err) {
    console.error("Failed to load audit entries", err);
  }
}

function renderAuditStream(entries) {
  const stream = document.getElementById("audit-stream");
  stream.innerHTML = "";

  if (entries.length === 0) {
    stream.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 32px;">No audit logs recorded yet.</div>`;
    return;
  }

  entries.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "audit-card";
    const statusClass = entry.status || "ok";
    const timeFormatted = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : "--";

    card.innerHTML = `
      <div class="audit-left">
        <span class="audit-status ${statusClass}">${escapeHtml(statusClass.toUpperCase())}</span>
        <strong>${escapeHtml(entry.action)}</strong>
      </div>
      <span class="audit-time">${timeFormatted}</span>
    `;

    stream.appendChild(card);
  });
}

// =============================================================================
// Utilities
// =============================================================================

function escapeHtml(str) {
  if (typeof str !== "string") str = String(str);
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
