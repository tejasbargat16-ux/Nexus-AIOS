/**
 * NEXUS AIOS - WEB CONSOLE APPLICATION (Phase 3)
 * Client-side Controller for Intent Planning, Tools, Persistent Memory,
 * Autonomous Task Scheduler, and Proactive Security Guard.
 */

const API_BASE = ""; // Relative to host
let currentTools = [];

// =============================================================================
// Initialization & Tab Navigation
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initChat();
  initGuard();
  initScheduler();
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
      if (target === "guard") loadGuardData();
      if (target === "scheduler") loadScheduledTasks();
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

    // Update Badges & Guard Pill
    const toolsBadge = document.getElementById("tools-count-badge");
    if (data.components?.tools_registered !== undefined) {
      toolsBadge.textContent = data.components.tools_registered;
    }

    const factsBadge = document.getElementById("facts-count-badge");
    if (data.components?.stored_facts !== undefined) {
      factsBadge.textContent = data.components.stored_facts;
    }

    const tasksBadge = document.getElementById("tasks-count-badge");
    if (data.components?.scheduled_tasks !== undefined) {
      tasksBadge.textContent = data.components.scheduled_tasks;
    }

    const score = data.components?.security_score ?? 100;
    const level = data.components?.security_level || "optimal";
    const guardBadge = document.getElementById("guard-score-badge");
    if (guardBadge) guardBadge.textContent = `${score}%`;

    const guardPillText = document.getElementById("guard-pill-text");
    const guardPill = document.getElementById("guard-status-pill");
    if (guardPillText) {
      guardPillText.textContent = `${score}% ${level.charAt(0).toUpperCase() + level.slice(1)}`;
      guardPill.className = `guard-pill ${level}`;
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
          <span>⚡ Tool Executed: <strong>${escapeHtml(meta.tool_result.action || "")}</strong></span>
          <span class="status-badge ${meta.tool_result.status === "ok" ? "ok" : "err"}">${meta.tool_result.status || "ok"}</span>
        </div>
        <pre>${escapeHtml(JSON.stringify(meta.tool_result.result, null, 2))}</pre>
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

  const guard = data.guard || {};
  const actionName = guard.action || data.action || "restricted_action";
  const params = guard.params || data.params || {};

  card.innerHTML = `
    <div class="security-confirm-card">
      <div class="confirm-title">
        <span>⚠️ Security Guard Authorization Required</span>
      </div>
      <p>The system planned to execute protected action <strong>${escapeHtml(actionName)}</strong>:</p>
      <pre style="margin: 8px 0; background: rgba(0,0,0,0.5); padding: 8px; border-radius: 4px; font-size: 0.8rem;">${escapeHtml(JSON.stringify(params, null, 2))}</pre>
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
    appendMessage("ai", `Action '${actionName}' was declined by user.`, { provider: "guard" });
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
    <div class="pulse-dot" style="display: inline-block;"></div> Planning & Checking Permissions...
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
// 2. Security Guard (Phase 3)
// =============================================================================

function initGuard() {
  document.getElementById("run-guard-scan-btn").addEventListener("click", async () => {
    const btn = document.getElementById("run-guard-scan-btn");
    btn.disabled = true;
    btn.textContent = "Scanning...";
    try {
      await fetch(`${API_BASE}/guard/scan`, { method: "POST" });
      await loadGuardData();
    } catch (err) {
      alert(`Scan failed: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "⚡ Run Security Scan";
    }
  });

  document.getElementById("clear-alerts-btn").addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/guard/alerts/clear`, { method: "POST" });
      await loadGuardData();
    } catch (err) {
      alert(`Clear failed: ${err.message}`);
    }
  });
}

async function loadGuardData() {
  try {
    const [statusRes, alertsRes] = await Promise.all([
      fetch(`${API_BASE}/guard/status`),
      fetch(`${API_BASE}/guard/alerts?limit=20`),
    ]);

    const statusData = await statusRes.json();
    const alertsData = await alertsRes.json();

    const posture = statusData.posture || statusData;
    const score = posture.score ?? 100;
    const level = posture.level || "optimal";
    const metrics = posture.metrics || {};
    const alerts = alertsData.alerts || [];

    // Update Posture Card
    const scoreEl = document.getElementById("posture-score");
    if (scoreEl) scoreEl.textContent = score;

    const tagEl = document.getElementById("posture-tag");
    if (tagEl) {
      tagEl.textContent = level.toUpperCase();
      tagEl.className = `posture-tag ${level}`;
    }

    const descEl = document.getElementById("posture-desc");
    if (descEl) {
      if (level === "optimal") {
        descEl.textContent = "All system tripwires, audit streams, and host resources are well within safe operating bounds.";
      } else if (level === "warning") {
        descEl.textContent = "Elevated resource consumption or recent permission denials detected. Review alerts below.";
      } else {
        descEl.textContent = "Critical security alert or resource exhaustion detected. Immediate administrator review recommended.";
      }
    }

    // Update Resource Metrics
    const cpuVal = metrics.cpu_percent ?? 0;
    const memVal = metrics.memory_percent ?? 0;
    const diskVal = metrics.disk_percent ?? 0;
    const procVal = metrics.process_count ?? 0;

    document.getElementById("metric-cpu-val").textContent = `${cpuVal}%`;
    document.getElementById("meter-cpu").style.width = `${Math.min(100, cpuVal)}%`;

    document.getElementById("metric-mem-val").textContent = `${memVal}% (${metrics.memory_used_mb || 0} / ${metrics.memory_total_mb || 0} MB)`;
    document.getElementById("meter-mem").style.width = `${Math.min(100, memVal)}%`;

    document.getElementById("metric-disk-val").textContent = `${diskVal}% (${metrics.disk_free_gb || 0} GB free)`;
    document.getElementById("meter-disk").style.width = `${Math.min(100, diskVal)}%`;

    document.getElementById("metric-proc-val").textContent = `${procVal} active processes`;

    // Update Alerts List
    const alertsList = document.getElementById("alerts-list");
    alertsList.innerHTML = "";

    const alertsBadge = document.getElementById("alerts-count-badge");
    alertsBadge.textContent = `${alerts.length} Alert${alerts.length === 1 ? "" : "s"}`;

    if (alerts.length === 0) {
      alertsList.innerHTML = `<div class="empty-state">✓ No active security alerts or tripwire triggers. System is running securely.</div>`;
    } else {
      alerts.forEach((alert) => {
        const item = document.createElement("div");
        item.className = `alert-item ${alert.severity || "info"}`;
        const timeStr = alert.timestamp ? new Date(alert.timestamp * 1000).toLocaleTimeString() : "--";

        item.innerHTML = `
          <div class="alert-header">
            <span class="alert-sev-badge ${alert.severity || "info"}">${(alert.severity || "info").toUpperCase()}</span>
            <span class="alert-source">[${escapeHtml(alert.source || "guard")}]</span>
            <span class="alert-time">${timeStr}</span>
          </div>
          <div class="alert-msg">${escapeHtml(alert.message)}</div>
        `;
        alertsList.appendChild(item);
      });
    }
  } catch (err) {
    console.error("Failed to load guard data", err);
  }
}

// =============================================================================
// 3. Autonomous Task Scheduler (Phase 3)
// =============================================================================

function initScheduler() {
  document.getElementById("refresh-tasks-btn").addEventListener("click", loadScheduledTasks);

  const modal = document.getElementById("add-task-modal");
  document.getElementById("open-add-task-modal").addEventListener("click", () => {
    modal.classList.add("open");
  });
  document.getElementById("close-task-modal").addEventListener("click", () => {
    modal.classList.remove("open");
  });
  document.getElementById("cancel-task-btn").addEventListener("click", () => {
    modal.classList.remove("open");
  });

  // Action type selector toggle
  const actionSelect = document.getElementById("task-action-type");
  const toolField = document.getElementById("task-tool-field");
  const intentField = document.getElementById("task-intent-field");

  actionSelect.addEventListener("change", () => {
    const val = actionSelect.value;
    if (val === "tool") {
      toolField.style.display = "block";
      intentField.style.display = "none";
    } else if (val === "intent") {
      toolField.style.display = "none";
      intentField.style.display = "block";
    } else {
      toolField.style.display = "none";
      intentField.style.display = "none";
    }
  });

  // Add Task Form submission
  document.getElementById("add-task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("task-name").value.trim();
    const action_type = actionSelect.value;
    const interval_seconds = parseInt(document.getElementById("task-interval").value, 10);

    let payload = {};
    if (action_type === "tool") {
      const toolName = document.getElementById("task-tool-name").value.trim() || "network.check";
      payload = { action: toolName, params: {} };
    } else if (action_type === "intent") {
      const intentText = document.getElementById("task-intent-text").value.trim();
      payload = { text: intentText };
    } else if (action_type === "system") {
      payload = { action: "guard.scan" };
    }

    try {
      const res = await fetch(`${API_BASE}/scheduler/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, action_type, payload, interval_seconds, enabled: true }),
      });
      if (!res.ok) throw new Error("Failed to create task");

      modal.classList.remove("open");
      document.getElementById("add-task-form").reset();
      loadScheduledTasks();
    } catch (err) {
      alert(`Error creating task: ${err.message}`);
    }
  });
}

async function loadScheduledTasks() {
  try {
    const res = await fetch(`${API_BASE}/scheduler/tasks`);
    const data = await res.json();
    renderTasksGrid(data.tasks || []);
  } catch (err) {
    console.error("Failed to load tasks", err);
  }
}

function renderTasksGrid(tasks) {
  const grid = document.getElementById("tasks-grid");
  grid.innerHTML = "";

  if (tasks.length === 0) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1;">No scheduled tasks registered. Click '+ Add Scheduled Task' to create one.</div>`;
    return;
  }

  tasks.forEach((task) => {
    const card = document.createElement("div");
    card.className = `task-card ${task.enabled ? "active" : "disabled"}`;

    const isEnabled = task.enabled;
    const statusClass = task.last_status === "ok" ? "ok" : (task.last_status === "pending" ? "pending" : "error");

    card.innerHTML = `
      <div class="task-card-header">
        <div>
          <span class="task-state-indicator ${isEnabled ? "enabled" : "disabled"}"></span>
          <span class="task-name">${escapeHtml(task.name)}</span>
        </div>
        <span class="task-id-tag">${escapeHtml(task.id)}</span>
      </div>

      <div class="task-meta-row">
        <span class="task-type-badge">${escapeHtml(task.action_type.toUpperCase())}</span>
        <span class="task-interval-badge">Every ${task.interval_seconds}s</span>
        <span class="task-due-badge">${isEnabled ? `Due in ${Math.round(task.due_in_seconds)}s` : "Paused"}</span>
      </div>

      <div class="task-stats-box">
        <div class="stat-line">
          <span>Execution Count:</span>
          <strong>${task.run_count}</strong>
        </div>
        <div class="stat-line">
          <span>Status:</span>
          <span class="status-pill-small ${statusClass}">${task.last_status.toUpperCase()}</span>
        </div>
        ${task.last_result ? `<div class="stat-result">${escapeHtml(task.last_result)}</div>` : ""}
      </div>

      <div class="task-actions-row">
        <button class="btn-task-action run-btn" title="Trigger execution now">▶ Run Now</button>
        <button class="btn-task-action toggle-btn" title="Toggle pause or resume">${isEnabled ? "⏸ Pause" : "▶ Resume"}</button>
        <button class="btn-task-action delete-btn" title="Delete task">🗑</button>
      </div>
    `;

    // Action listeners
    card.querySelector(".run-btn").addEventListener("click", async () => {
      try {
        const btn = card.querySelector(".run-btn");
        btn.textContent = "...";
        await fetch(`${API_BASE}/scheduler/tasks/${encodeURIComponent(task.id)}/run`, { method: "POST" });
        loadScheduledTasks();
      } catch (err) {
        alert(`Run failed: ${err.message}`);
      }
    });

    card.querySelector(".toggle-btn").addEventListener("click", async () => {
      try {
        await fetch(`${API_BASE}/scheduler/tasks/${encodeURIComponent(task.id)}/toggle`, { method: "POST" });
        loadScheduledTasks();
      } catch (err) {
        alert(`Toggle failed: ${err.message}`);
      }
    });

    card.querySelector(".delete-btn").addEventListener("click", async () => {
      if (!confirm(`Delete scheduled task '${task.name}'?`)) return;
      try {
        await fetch(`${API_BASE}/scheduler/tasks/${encodeURIComponent(task.id)}`, { method: "DELETE" });
        loadScheduledTasks();
      } catch (err) {
        alert(`Delete failed: ${err.message}`);
      }
    });

    grid.appendChild(card);
  });
}

// =============================================================================
// 4. Tools Catalog & Direct Execution
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
// 5. Memory & Facts
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
    list.innerHTML = `<div class="empty-state">No memory facts recorded yet.</div>`;
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
    list.innerHTML = `<div class="empty-state">No matches found for search query.</div>`;
    return;
  }

  results.forEach((r) => {
    const item = document.createElement("div");
    item.className = "fact-item";
    item.innerHTML = `
      <div>
        <div class="fact-key">${escapeHtml(r.key || `Memory #${r.id}`)}</div>
        <div class="fact-value">${escapeHtml(JSON.stringify(r.content || r.snippet))}</div>
      </div>
      <div>
        <span class="meta-duration">Score: ${r.score || r.relevance}</span>
      </div>
    `;
    list.appendChild(item);
  });
}

// =============================================================================
// 6. Audit & Security Stream
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
    stream.innerHTML = `<div class="empty-state">No audit logs recorded yet.</div>`;
    return;
  }

  entries.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "audit-card";
    const statusClass = entry.status || "ok";
    const timeFormatted = entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleTimeString() : "--";

    card.innerHTML = `
      <div class="audit-left">
        <span class="audit-status ${statusClass}">${escapeHtml(statusClass.toUpperCase())}</span>
        <strong>${escapeHtml(entry.event || entry.action)}</strong>
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
