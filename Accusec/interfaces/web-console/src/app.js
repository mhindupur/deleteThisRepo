const TITLES = {
  ask: "Ask AccuSec",
  workflow: "Change workflow",
  inventory: "Organizational Memory inventory",
  endpoints: "Endpoints and identities",
  organization: "Organization",
  folders: "Folders",
  iam: "IAM policies",
  agents: "AI Engineers",
  mcp: "MCP registry",
  entitlements: "Endpoint entitlements",
  memory: "Organizational Memory ACLs",
  audit: "Audit reconstruct",
  dayn: "Day 0 / Day 1 / Day N",
};

const thread = document.getElementById("thread");
const connectionStatus = document.getElementById("connection-status");
const intentBox = document.getElementById("intent");
const derivedAccount = document.getElementById("derived-account");

let lastTask = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail || data.message || res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function currentPrincipal() {
  return document.getElementById("principal-select")?.value || "alice";
}

function currentIdentity() {
  return document.getElementById("identity-select")?.value || "";
}

function optionList(items, valueKey, labelFn, selected) {
  return items
    .map((item) => {
      const value = item[valueKey];
      const selectedAttr = value === selected ? " selected" : "";
      return `<option value="${value}"${selectedAttr}>${labelFn(item)}</option>`;
    })
    .join("");
}

function showView(name) {
  document.querySelectorAll(".view").forEach((el) => {
    const on = el.id === `view-${name}`;
    el.classList.toggle("active", on);
    el.hidden = !on;
  });
  document.querySelectorAll(".nav-btn").forEach((el) => el.classList.toggle("active", el.dataset.view === name));
  document.getElementById("view-title").textContent = TITLES[name] || name;
  if (name === "inventory") loadInventory().catch((err) => showInventoryError(err));
  if (name === "workflow") renderPipeline(lastTask);
  if (name === "ask") thread.scrollTop = thread.scrollHeight;
}

function addBubble(html, cls = "system") {
  const el = document.createElement("article");
  el.className = `bubble ${cls}`;
  el.innerHTML = html;
  thread.append(el);
  thread.scrollTop = thread.scrollHeight;
  return el;
}

function instanceTable(rows) {
  if (!rows || !rows.length) return "<p class='meta'>No instances in Organizational Memory for this filter.</p>";
  const body = rows
    .map(
      (row) => `<tr>
        <td><code>${row.instance_id || ""}</code></td>
        <td>${row.name || ""}</td>
        <td>${row.instance_type || ""}</td>
        <td>${row.region || ""}</td>
        <td>${row.vpc_id || ""}</td>
        <td>${row.state || ""}</td>
        <td>${row.source || ""}</td>
      </tr>`
    )
    .join("");
  return `<table><thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Region</th><th>VPC</th><th>State</th><th>Source</th></tr></thead><tbody>${body}</tbody></table>`;
}

function volumeTable(result) {
  const rows = result.volumes || [];
  if (!rows.length) return "<p class='meta'>No attached volumes returned.</p>";
  const body = rows
    .map(
      (row) => `<tr>
        <td><code>${row.volume_id || ""}</code></td>
        <td>${row.device || ""}</td>
        <td>${row.size_gb != null ? row.size_gb + " GiB" : ""}</td>
        <td>${row.volume_type || ""}</td>
        <td>${row.state || ""}</td>
      </tr>`
    )
    .join("");
  const total = result.total_size_gb != null ? `<p class="meta">Total storage: ${result.total_size_gb} GiB</p>` : "";
  return `${total}<table><thead><tr><th>Volume</th><th>Device</th><th>Size</th><th>Type</th><th>State</th></tr></thead><tbody>${body}</tbody></table>`;
}

function bindApproval(el, task, result) {
  el.querySelectorAll("button[data-approve]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const next = await api(`/api/tasks/${task.task_id}/approve`, {
          method: "POST",
          body: JSON.stringify({
            approval_id: result.approval_id,
            approved: btn.dataset.approve === "yes",
            principal_id: currentPrincipal(),
          }),
        });
        renderTask(next);
      } catch (err) {
        addBubble(`<strong>Approval failed</strong><p>${err.message}</p>`, "bad");
      }
    });
  });
}

function pipelinePhase(task) {
  if (!task) return null;
  const state = task.state;
  const status = (task.result && task.result.status) || "";
  if (status === "needs_clarification" || state === "awaiting_context") return "observe";
  if (state === "planning" || state === "created") return "reason";
  if (state === "awaiting_authorization") return "authorize";
  if (status === "awaiting_approval" || state === "awaiting_approval") return "approve";
  if (state === "running") return "execute";
  if (state === "validating") return "validate";
  if (state === "succeeded" || state === "failed" || state === "cancelled") return "record";
  return "reason";
}

function renderPipeline(task) {
  const phase = pipelinePhase(task);
  const order = ["observe", "reason", "authorize", "approve", "execute", "validate", "record"];
  const idx = order.indexOf(phase);
  document.querySelectorAll("#pipeline li").forEach((el) => {
    const pos = order.indexOf(el.dataset.phase);
    el.classList.toggle("active", el.dataset.phase === phase);
    el.classList.toggle("done", idx >= 0 && pos < idx);
  });
  const box = document.getElementById("last-task");
  if (box) box.textContent = task ? JSON.stringify(task, null, 2) : "No task in this browser session yet. Use Ask.";
}

function renderTask(task) {
  lastTask = task;
  renderPipeline(task);
    const result = task.result || {};
  if (result.status === "awaiting_approval") {
    const hydrate = result.action === "hydrate_volumes" || task.operation === "storage.volume.read";
    const expand = result.action === "expand_volume" || task.operation === "storage.volume.expand";
    const start = result.action === "start_instance" || task.operation === "compute.instance.start";
    const stop = result.action === "stop_instance" || task.operation === "compute.instance.stop";
    const target = (result.target && result.target.instances) || [];
    const confirmLabel = hydrate
      ? "Pull from AWS"
      : expand
        ? "Confirm expand"
        : start
          ? "Confirm start"
          : stop
            ? "Confirm stop"
            : "Confirm";
    const title = hydrate
      ? "Pull volume details from AWS?"
      : expand
        ? "Expand volume on AWS?"
        : start
          ? "Start instance on AWS?"
          : stop
            ? "Stop instance on AWS?"
            : "HITL confirmation required";
    const extra = hydrate
      ? `<p class="meta">${result.instance_id || ""} · ${result.instance_name || ""} · ${result.region || ""}</p>`
      : expand
        ? volumeTable(result)
        : instanceTable(target);
    const gov = [result.agent_id, result.project_id, result.datacenter_id, result.endpoint_identity_id]
      .filter(Boolean)
      .join(" · ");
    const el = addBubble(
      `<strong>${title}</strong>
       <p class="meta">${result.reason || "AccuSec allowed this change only with approval."}</p>
       ${gov ? `<p class="meta">${gov}</p>` : ""}
       ${extra}
       <div class="actions">
         <button data-approve="yes">${confirmLabel}</button>
         <button class="danger" data-approve="no">Reject</button>
       </div>`,
      "warn"
    );
    bindApproval(el, task, result);
    return;
  }
  if (result.status === "needs_clarification") {
    const candidates = (result.candidates && result.candidates.instances) || [];
    const el = addBubble(
      `<strong>Choose an instance</strong>
       <p class="meta">${(result.questions || []).join(" ")}</p>
       ${instanceTable(candidates)}
       <div class="actions">
         <input placeholder="i-..." />
         <button data-clarify>Continue</button>
       </div>`,
      "warn"
    );
    el.querySelector("[data-clarify]").addEventListener("click", async () => {
      const instanceId = el.querySelector("input").value.trim();
      try {
        const next = await api(`/api/tasks/${task.task_id}/clarify`, {
          method: "POST",
          body: JSON.stringify({ instance_id: instanceId }),
        });
        renderTask(next);
      } catch (err) {
        addBubble(`<strong>Clarification failed</strong><p>${err.message}</p>`, "bad");
      }
    });
    return;
  }
  if (result.status === "denied" || result.status === "not_found" || task.state === "failed") {
    addBubble(
      `<strong>${result.status || task.state}</strong><p>${result.reason || "Request did not complete."}</p>`,
      "bad"
    );
    return;
  }
  if (result.volumes) {
    addBubble(
      `<strong>${task.operation}</strong>
       <p class="meta">state ${task.state}${result.source ? " · source " + result.source : ""}${result.instance_name ? " · " + result.instance_name : ""}</p>
       ${volumeTable(result)}`
    );
    return;
  }
  const rows = result.instances || (result.target && result.target.instances) || [];
  addBubble(
    `<strong>${task.operation}</strong>
     <p class="meta">state ${task.state}${result.source ? " · source " + result.source : ""}${result.lifecycle_state ? " · now " + result.lifecycle_state : ""}</p>
     ${rows.length ? instanceTable(rows) : `<pre class="status-box">${JSON.stringify(result, null, 2)}</pre>`}`
  );
}

function accountFromArn(arn) {
  const match = String(arn || "").match(/arn:aws[-a-z]*:iam::(\d{12}):role\//i);
  return match ? match[1] : "";
}

function fillKv(el, pairs) {
  el.innerHTML = pairs.map(([k, v]) => `<dt>${k}</dt><dd>${v || "—"}</dd>`).join("");
}

function showInventoryError(err) {
  document.getElementById("inventory-table").innerHTML = `<p class="meta">${err.message}</p>`;
}

async function loadInventory() {
  const region = document.getElementById("inv-region").value.trim();
  const instanceType = document.getElementById("inv-type").value.trim();
  const state = document.getElementById("inv-state").value.trim();
  const params = new URLSearchParams();
  if (region) params.set("region", region);
  if (instanceType) params.set("instance_type", instanceType);
  if (state) params.set("state", state);
  const qs = params.toString();
  const data = await api(`/api/entities${qs ? "?" + qs : ""}`);
  document.getElementById("inventory-table").innerHTML =
    `<p class="meta">${data.count} authorized instances · policy ${data.policy} · source ${data.source}</p>` +
    instanceTable(data.instances);
}

async function refreshConnection() {
  const health = await api("/api/health");
  const org = health.org || {};
  document.getElementById("header-org").textContent =
    `${org.tenant_id || health.tenant_id} · ${org.project_id || health.project_id} · ${org.datacenter_id || health.datacenter_id} · agent ${health.agent_id}`;
  const principalSelect = document.getElementById("principal-select");
  const identitySelect = document.getElementById("identity-select");
  const previousPrincipal = principalSelect.value || "alice";
  const previousIdentity = identitySelect.value;
  principalSelect.innerHTML = optionList(
    health.principals || [],
    "principal_id",
    (item) => `${item.display_name} (${item.roles.join(", ")})`,
    previousPrincipal
  );
  identitySelect.innerHTML = optionList(
    [{ endpoint_identity_id: "", identity_type: "auto", display_name: "Auto-select" }].concat(health.identities || []),
    "endpoint_identity_id",
    (item) =>
      item.endpoint_identity_id
        ? `${item.identity_type} · ${item.display_name || item.endpoint_identity_id}`
        : "Auto-select",
    previousIdentity
  );
  document.getElementById("connection-pill").textContent = health.connected ? "AWS connected" : "AWS disconnected";

  const orgKv = document.getElementById("org-kv");
  if (orgKv) {
    fillKv(orgKv, [
      ["tenant", `${org.tenant_name} (${org.tenant_id})`],
      ["project", `${org.project_name} (${org.project_id})`],
      ["datacenter", `${org.datacenter_name} (${org.datacenter_id})`],
      ["workspace alias", org.workspace_id],
      ["agent_id", health.agent_id],
    ]);
  }

  const principalTable = document.getElementById("principal-table");
  if (principalTable) {
    const rows = (health.principals || [])
      .map(
        (item) =>
          `<tr><td>${item.display_name}</td><td><code>${item.principal_id}</code></td><td>${item.principal_type}</td><td>${item.roles.join(", ")}</td></tr>`
      )
      .join("");
    principalTable.innerHTML = `<table><thead><tr><th>Name</th><th>ID</th><th>Type</th><th>Roles</th></tr></thead><tbody>${rows}</tbody></table>`;
  }

  const identityTable = document.getElementById("identity-table");
  if (identityTable) {
    const rows = (health.identities || [])
      .map(
        (item) =>
          `<tr><td>${item.identity_type}</td><td>${item.display_name}</td><td><code>${item.endpoint_identity_id}</code></td><td>${item.status}</td><td><code>${item.secret_ref}</code></td></tr>`
      )
      .join("");
    identityTable.innerHTML = rows
      ? `<table><thead><tr><th>Type</th><th>Name</th><th>ID</th><th>Status</th><th>secret-ref</th></tr></thead><tbody>${rows}</tbody></table>`
      : "<p class='meta'>No Endpoint Access Identities registered.</p>";
  }

  const conn = await api("/api/connection");
  connectionStatus.textContent = JSON.stringify(conn, null, 2);
  if (conn.account_id) derivedAccount.textContent = `Account from connection: ${conn.account_id}`;
  if (conn.auth && conn.auth.role_arn) {
    document.querySelector("input[name='role_arn']").value = conn.auth.role_arn;
  }
  if (conn.regions && conn.regions.length) {
    document.querySelector("input[name='regions']").value = conn.regions.join(", ");
    if (!document.getElementById("sync-region").value) {
      document.getElementById("sync-region").value = conn.regions[0];
    }
  }
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

document.querySelector("input[name='role_arn']").addEventListener("input", (event) => {
  const account = accountFromArn(event.target.value);
  derivedAccount.textContent = account ? `Account from ARN: ${account}` : "Account will be read from the ARN.";
});

document.getElementById("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  try {
    const payload = Object.fromEntries(form.entries());
    const result = await api("/api/connection", { method: "POST", body: JSON.stringify(payload) });
    showView("ask");
    addBubble(`<strong>Role connected</strong><p class="meta">${result.secret_ref} · account ${result.account_id}</p>`);
    await refreshConnection();
  } catch (err) {
    showView("ask");
    addBubble(`<strong>Connect failed</strong><p>${err.message}</p>`, "bad");
  }
});

document.getElementById("sync-btn").addEventListener("click", async () => {
  const region = document.getElementById("sync-region").value.trim();
  try {
    const result = await api("/api/sync", { method: "POST", body: JSON.stringify({ region }) });
    showView("ask");
    addBubble(
      `<strong>Inventory sync ${result.status}</strong><p class="meta">${result.region} · upserted ${result.upserted} · missing ${result.missing}</p>`
    );
    await refreshConnection();
  } catch (err) {
    showView("ask");
    addBubble(`<strong>Sync failed</strong><p>${err.message}</p>`, "bad");
  }
});

document.getElementById("inv-refresh").addEventListener("click", () => {
  loadInventory().catch((err) => showInventoryError(err));
});

async function sendAsk() {
  const intent = intentBox.value.trim();
  if (!intent) return;
  addBubble(`<p>${intent.replace(/</g, "&lt;")}</p>`, "user");
  intentBox.value = "";
  try {
    const task = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({
        intent,
        principal_id: currentPrincipal(),
        endpoint_identity_id: currentIdentity() || null,
      }),
    });
    renderTask(task);
  } catch (err) {
    addBubble(`<strong>Ask failed</strong><p>${err.message}</p>`, "bad");
  }
}

document.getElementById("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendAsk();
});

intentBox.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendAsk();
  }
});

refreshConnection().catch((err) => {
  connectionStatus.textContent = err.message;
});
