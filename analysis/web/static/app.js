/* 仓库全面分析 · Web 控制台（原生 JS，无构建链）
 * 视图：任务列表 / 任务详情（工作流 + SSE 事件流 + 增量预览）
 */
"use strict";

const $ = (sel) => document.querySelector(sel);

const state = {
  view: "list",
  taskId: null,
  es: null,            // EventSource
  listTimer: null,
  previewTimer: null,
};

const STAGES = [
  { title: "① 确定性采集", names: ["collect.overview", "collect.structure", "collect.git_context", "collect.dependencies", "collect.quality", "collect.security", "collect.performance", "collect.docs", "collect.tests"] },
  { title: "② AI 分析（claude headless）", names: ["ai.architecture", "ai.business_knowledge", "ai.conclusions"] },
  { title: "③ 评分与总结", names: ["scoring", "ai.summary"] },
  { title: "④ 归档", names: ["report.archive"] },
];

const EV_ICON = {
  task_queued: "📥", task_started: "▶️", task_completed: "✅", task_failed: "❌",
  task_canceled: "🚫", subtask_started: "🔹", subtask_completed: "✔",
  subtask_failed: "✖", subtask_retry: "🔁", subtask_skipped: "⚠️", log: "·",
};

/* ---------- 通用 ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---------- 健康状态 ---------- */
async function refreshHealth() {
  try {
    const h = await api("/api/health");
    const el = $("#daemon-status");
    const ver = h.version ? `v${h.version} · ` : "";
    el.textContent = ver + (h.daemon_alive ? `daemon: 运行中 (pid=${h.daemon_pid})` : "daemon: 未运行（发起任务时自动拉起）");
    el.className = "daemon " + (h.daemon_alive ? "alive" : "dead");
  } catch (_) {}
}

function showBanner(text, kind) {
  let b = $("#banner");
  if (!b) {
    b = document.createElement("div");
    b.id = "banner";
    document.body.prepend(b);
  }
  b.textContent = text;
  b.className = "banner " + (kind || "ok");
  clearTimeout(b._t);
  b._t = setTimeout(() => b.remove(), 8000);
}

/* ---------- 列表视图 ---------- */
async function loadTasks() {
  if (state.view !== "list") return;
  try {
    const { tasks } = await api("/api/tasks");
    const tbody = $("#tasks-table tbody");
    $("#tasks-empty").classList.toggle("hidden", tasks.length > 0);
    $("#tasks-table").classList.toggle("hidden", tasks.length === 0);
    tbody.innerHTML = tasks.map((t) => {
      const p = t.progress || {};
      const pct = p.total ? Math.round((p.completed / p.total) * 100) : 0;
      return `<tr class="clickable" data-id="${esc(t.task_id)}">
        <td><code>${esc(t.task_id)}</code></td>
        <td>${esc(t.org)}/${esc(t.repo)}</td>
        <td><span class="badge st-${t.status}">${t.status}</span>${modeTag(t)}</td>
        <td><span class="progress"><i style="width:${pct}%"></i></span> ${p.completed}/${p.total}</td>
        <td>${esc((t.created_at || "").replace("T", " "))}</td>
        <td>${t.duration_seconds != null ? t.duration_seconds + "s" : "-"}</td>
        <td>${t.report && t.report.html ? "📄" : ""}</td></tr>`;
    }).join("");
    tbody.querySelectorAll("tr").forEach((tr) =>
      tr.addEventListener("click", () => openDetail(tr.dataset.id)));
  } catch (e) { console.error(e); }
}

/* ---------- 详情视图 ---------- */
async function openDetail(taskId) {
  state.view = "detail";
  state.taskId = taskId;
  $("#view-list").classList.add("hidden");
  $("#view-detail").classList.remove("hidden");
  $("#events").innerHTML = "";
  connectSSE(taskId);
  await refreshDetail();
  clearInterval(state.previewTimer);
  state.previewTimer = setInterval(refreshDetail, 3000);
}

function backToList() {
  state.view = "list";
  state.taskId = null;
  if (state.es) { state.es.close(); state.es = null; }
  clearInterval(state.previewTimer);
  $("#view-detail").classList.add("hidden");
  $("#view-list").classList.remove("hidden");
  loadTasks();
}

async function refreshDetail() {
  if (!state.taskId) return;
  try {
    const task = await api(`/api/tasks/${state.taskId}`);
    renderTaskHead(task);
    renderWorkflow(task);
    renderActions(task);
    const pv = await api(`/api/tasks/${state.taskId}/preview`);
    renderPreview(pv);
    if (["completed", "failed", "canceled"].includes(task.status)) {
      clearInterval(state.previewTimer);
      state.previewTimer = null;
    }
  } catch (e) { console.error(e); }
}

function modeTag(t) {
  // 执行范围标注：桩/无AI/mock 的 AI 章节不是模型结论（DESIGN D16/D17）
  if (t.no_ai) return '<span class="mode-tag" title="AI 子任务已跳过（--no-ai），评分按缺失维度归一化">无AI</span>';
  if (t.ai_stub) return '<span class="mode-tag" title="AI 章节为 schema-valid 桩数据（--ai-stub），不可作为分析结论">桩</span>';
  if (t.mock) return '<span class="mode-tag" title="mock 联调：子任务为模拟执行">mock</span>';
  return "";
}

function renderTaskHead(t) {
  $("#detail-title").innerHTML = `<code>${esc(t.task_id)}</code> <span class="badge st-${t.status}">${t.status}</span>${modeTag(t)}`;
  $("#task-meta").innerHTML =
    `仓库 ${esc(t.org)}/${esc(t.repo)} · 基线 <code>${esc((t.commit_sha || "?").slice(0, 12))}</code>` +
    (t.ref ? `（ref=${esc(t.ref)}）` : "") +
    ` · 进度 ${t.progress.completed}/${t.progress.total}` +
    (t.progress.failed ? ` · <b style="color:var(--bad)">${t.progress.failed} 失败</b>` : "") +
    (t.progress.skipped ? ` · <b style="color:var(--warn)">${t.progress.skipped} 跳过</b>` : "") +
    (t.duration_seconds != null ? ` · 耗时 ${t.duration_seconds}s` : "") +
    (t.error ? `<br>⚠️ ${esc(t.error)}` : "");
}

function renderActions(t) {
  const el = $("#detail-actions");
  let html = "";
  if (["queued", "running"].includes(t.status))
    html += `<button class="danger" onclick="cancelTask(event)">取消</button> `;
  if (["completed", "failed", "canceled"].includes(t.status))
    html += `<button onclick="retryTask()">♻️ 重试失败项</button> `;
  if (t.report && t.report.html) {
    const rel = t.report.html.split("/reports/")[1];
    html += `<a class="report-link" href="/reports/${rel ? esc(rel) : ""}" target="_blank">📄 打开归档报告</a>`;
  }
  el.innerHTML = html;
}

function renderWorkflow(t) {
  const html = STAGES.map((stage, i) => {
    const nodes = stage.names.map((name) => {
      const st = (t.subtasks || {})[name] || { status: "queued" };
      return `<div class="node ${st.status}" data-name="${name}" title="${esc(st.error || st.skip_reason || "")}">
        <div class="nm">${name}</div>
        <div class="st"><span>${st.status}</span><span>${st.duration_seconds != null ? st.duration_seconds + "s" : ""}${st.attempts > 1 ? " ·第" + st.attempts + "次" : ""}</span></div>
      </div>`;
    }).join("");
    return `<div class="stage"><h3>${stage.title}</h3><div class="nodes">${nodes}</div></div>` +
      (i < STAGES.length - 1 ? `<div class="stage-arrow">↓</div>` : "");
  }).join("");
  $("#workflow").innerHTML = html;
  $("#workflow").querySelectorAll(".node").forEach((n) =>
    n.addEventListener("click", () => showSubtask(n.dataset.name)));
}

async function showSubtask(name) {
  try {
    const pv = await api(`/api/tasks/${state.taskId}/preview`);
    const ch = pv.chapters[name];
    $("#subtask-detail").innerHTML = ch
      ? `<h3 style="font-size:13px"><code>${esc(name)}</code> — ${ch.status} ${ch.description ? "· " + esc(ch.description) : ""}</h3>
         <pre>${esc(JSON.stringify(ch.data ?? { note: ch.error || "（无产物）" }, null, 2))}</pre>`
      : "";
  } catch (e) { console.error(e); }
}

/* ---------- SSE 事件流 ---------- */
function connectSSE(taskId) {
  if (state.es) state.es.close();
  const es = new EventSource(`/api/tasks/${taskId}/stream`);
  state.es = es;
  es.onmessage = (e) => {
    try { appendEvent(JSON.parse(e.data)); } catch (_) {}
  };
  es.addEventListener("done", () => { es.close(); refreshDetail(); });
  es.onerror = () => { /* 任务终态后服务端关闭连接属正常 */ };
}

function appendEvent(ev) {
  const box = $("#events");
  const div = document.createElement("div");
  div.className = "ev " + (ev.type || "");
  const ts = (ev.ts || "").split("T")[1] || "";
  div.innerHTML = `<span class="ts">${ts}</span> ${EV_ICON[ev.type] || "·"} [${esc(ev.type)}]` +
    (ev.subtask ? ` <b>${esc(ev.subtask)}</b>` : "") +
    (ev.message ? ` ${esc(ev.message)}` : "") +
    (ev.duration_seconds != null ? ` (${ev.duration_seconds}s)` : "");
  box.appendChild(div);
  while (box.childNodes.length > 500) box.removeChild(box.firstChild);
  box.scrollTop = box.scrollHeight;
}

/* ---------- 增量预览 ---------- */
function renderPreview(pv) {
  const order = STAGES.flatMap((s) => s.names);
  $("#preview").innerHTML = order.map((name) => {
    const ch = pv.chapters[name] || {};
    const icon = { completed: "✅", running: "🔄", failed: "❌", skipped: "⚠️", queued: "⏳" }[ch.status] || "⏳";
    const hasData = ch.data && !ch.data._error;
    return `<details class="chap" ${ch.status === "running" ? "open" : ""}>
      <summary>${icon} <code>${esc(name)}</code>
        <span class="badge st-${ch.status}" style="margin-left:auto">${ch.status}</span></summary>
      ${ch.error ? `<div style="padding:8px 12px;color:var(--bad);font-size:12.5px">${esc(ch.error)}</div>` : ""}
      ${hasData ? `<pre>${esc(JSON.stringify(ch.data, null, 1))}</pre>` :
        (ch.status === "completed" ? "" : `<div style="padding:8px 12px;color:var(--muted);font-size:12.5px">${ch.status === "queued" ? "排队中…" : ch.status === "running" ? "分析中…" : ""}</div>`)}
    </details>`;
  }).join("");
}

/* ---------- 发起 / 控制 ---------- */
$("#start-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const msg = $("#start-msg");
  msg.className = ""; msg.textContent = "发起中…";
  try {
    const r = await api("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: f.target.value.trim(),
        ref: f.ref.value.trim() || null,
        mock: f.mock.checked,
      }),
    });
    msg.className = "ok"; msg.textContent = `✅ 任务已创建: ${r.task_id}`;
    f.target.value = ""; f.ref.value = "";
    await refreshHealth();
    openDetail(r.task_id);
  } catch (err) {
    msg.className = "err"; msg.textContent = "❌ " + err.message;
  }
});

// 取消：双击内联确认（不用 confirm()——可能被浏览器静默拦截，导致「点了没反应」）
let cancelArmed = false;
window.cancelTask = async function (ev) {
  const btn = ev && ev.target;
  if (!cancelArmed) {
    cancelArmed = true;
    if (btn) { btn.textContent = "再点一次确认取消"; btn.classList.add("armed"); }
    setTimeout(() => {
      cancelArmed = false;
      if (btn) { btn.textContent = "取消"; btn.classList.remove("armed"); }
    }, 4000);
    return;
  }
  cancelArmed = false;
  if (btn) { btn.disabled = true; btn.textContent = "取消中…"; }
  try {
    await api(`/api/tasks/${state.taskId}/cancel`, { method: "POST" });
    showBanner("✅ 已请求取消：在子任务边界生效（AI 子任务执行中时最长需等其完成；可用 CLI cancel 后 kill headless claude 立即中断）", "ok");
    refreshDetail();
  } catch (e) {
    showBanner("❌ 取消失败: " + e.message, "err");
    if (btn) { btn.disabled = false; btn.textContent = "取消"; }
  }
};

window.retryTask = async function () {
  try {
    await api(`/api/tasks/${state.taskId}/retry`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    });
    showBanner("♻️ 已重新入队（已完成子任务不重复执行）", "ok");
    refreshHealth();
    connectSSE(state.taskId);
    clearInterval(state.previewTimer);
    state.previewTimer = setInterval(refreshDetail, 3000);
    refreshDetail();
  } catch (e) { showBanner("❌ 重试失败: " + e.message, "err"); }
};

$("#back-btn").addEventListener("click", backToList);

/* ---------- 启动 ---------- */
refreshHealth();
setInterval(refreshHealth, 5000);
loadTasks();
state.listTimer = setInterval(loadTasks, 3000);
