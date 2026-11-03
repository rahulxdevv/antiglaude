/**
 * Antigravity Observer - Real-Time Dashboard Controller
 * Modern vanilla JavaScript handling SSE streaming, timeline waterfalls,
 * request tables, canvas charts, and diagnostic inspector.
 */

// Application State
const state = {
  activeConversationId: null,
  runtime: null,
  quota: null,
  conversations: [],
  timeline: [],
  requests: [],
  analytics: null,
  activeTab: 'timeline',
  filterThinkingOnly: false,
  filterToolsOnly: false,
  searchQuery: '',
};

// DOM References
const el = {
  connectionStatus: document.getElementById('connectionStatus'),
  promptCreditsLabel: document.getElementById('promptCreditsLabel'),
  exportBtn: document.getElementById('exportBtn'),
  exportMenu: document.getElementById('exportMenu'),
  refreshBtn: document.getElementById('refreshBtn'),
  globalSearchInput: document.getElementById('globalSearchInput'),

  // KPIs
  kpiModel: document.getElementById('kpiModel'),
  kpiModelId: document.getElementById('kpiModelId'),
  kpiPeakPrompt: document.getElementById('kpiPeakPrompt'),
  kpiTokensRow: document.getElementById('kpiTokensRow'),
  kpiThinkingSubtext: document.getElementById('kpiThinkingSubtext'),
  kpiTurns: document.getElementById('kpiTurns'),
  kpiToolsSubtext: document.getElementById('kpiToolsSubtext'),
  geminiWeeklyBar: document.getElementById('geminiWeeklyBar'),
  geminiWeeklyVal: document.getElementById('geminiWeeklyVal'),
  gemini5hBar: document.getElementById('gemini5hBar'),
  gemini5hVal: document.getElementById('gemini5hVal'),
  kpiQuotaReset: document.getElementById('kpiQuotaReset'),

  // Panes
  timelineContainer: document.getElementById('timelineContainer'),
  timelineStats: document.getElementById('timelineStats'),
  requestsTableBody: document.getElementById('requestsTableBody'),
  requestsCountBadge: document.getElementById('requestsCountBadge'),
  conversationsList: document.getElementById('conversationsList'),
  diagProcessInfo: document.getElementById('diagProcessInfo'),
  diagRpcInfo: document.getElementById('diagRpcInfo'),
  diagLogContent: document.getElementById('diagLogContent'),
  analyticsSummaryContent: document.getElementById('analyticsSummaryContent'),

  // Drawer
  inspectorDrawer: document.getElementById('inspectorDrawer'),
  drawerTitle: document.getElementById('drawerTitle'),
  drawerBadge: document.getElementById('drawerBadge'),
  drawerContent: document.getElementById('drawerContent'),
  closeDrawerBtn: document.getElementById('closeDrawerBtn'),

  // Filters
  filterThinkingOnly: document.getElementById('filterThinkingOnly'),
  filterToolsOnly: document.getElementById('filterToolsOnly'),
};

// --- INITIALIZATION ---
async function init() {
  setupEventListeners();
  await refreshAll();
  initLiveStream();
}

function setupEventListeners() {
  // Tab Navigation
  document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetId = `tab-${tab.dataset.tab}`;
      document.getElementById(targetId)?.classList.add('active');
      state.activeTab = tab.dataset.tab;

      if (state.activeTab === 'analytics') {
        renderCharts();
      }
    });
  });

  // Export Dropdown
  el.exportBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    el.exportMenu.classList.toggle('hidden');
  });
  document.addEventListener('click', () => el.exportMenu.classList.add('hidden'));

  // Refresh
  el.refreshBtn.addEventListener('click', refreshAll);

  // Search
  el.globalSearchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    if (state.activeTab === 'timeline') renderTimeline();
    if (state.activeTab === 'requests') renderRequests();
  });

  // Filters
  el.filterThinkingOnly.addEventListener('change', (e) => {
    state.filterThinkingOnly = e.target.checked;
    renderTimeline();
  });
  el.filterToolsOnly.addEventListener('change', (e) => {
    state.filterToolsOnly = e.target.checked;
    renderTimeline();
  });

  // Drawer Close
  el.closeDrawerBtn.addEventListener('click', closeDrawer);
}

// --- DATA FETCHING ---
async function refreshAll() {
  try {
    await fetchStatus();
    await fetchQuota();
    await fetchConversations();
    if (state.activeConversationId) {
      await fetchConversationDetails(state.activeConversationId);
    }
    await fetchRequests();
    await fetchAnalytics();
  } catch (err) {
    console.error('Error refreshing data:', err);
  }
}

async function fetchStatus() {
  const res = await fetch('/api/status');
  const data = await res.json();
  state.runtime = data.runtime;
  state.activeConversationId = data.active_conversation_id || state.activeConversationId;

  // Update Status Pill
  if (state.runtime && state.runtime.is_running) {
    el.connectionStatus.className = 'connection-pill status-connected';
    el.connectionStatus.querySelector('.status-label').textContent =
      `IDE Online (PID: ${state.runtime.language_server_pid || state.runtime.ide_pid}, RPC Port: ${state.runtime.rpc_port || '...' })`;
  } else {
    el.connectionStatus.className = 'connection-pill';
    el.connectionStatus.querySelector('.status-label').textContent = 'Antigravity IDE Inactive';
  }

  // Update Diagnostics
  el.diagProcessInfo.textContent = JSON.stringify(state.runtime, null, 2);
}

async function fetchQuota() {
  const res = await fetch('/api/quota');
  const data = await res.json();
  state.quota = data;

  if (data.prompt_credits) {
    const pc = data.prompt_credits;
    el.promptCreditsLabel.textContent = `Credits: ${Math.round(pc.available).toLocaleString()} / ${Math.round(pc.monthly).toLocaleString()} (${pc.remaining_percentage}%)`;
  }

  // Quota Buckets
  const groups = data.quota_groups || [];
  let resetText = 'Reset: Ready';
  groups.forEach(g => {
    const gname = g.display_name.toLowerCase();
    (g.buckets || []).forEach(b => {
      const bid = b.bucket_id.toLowerCase();
      const pct = Math.round(b.remaining_percentage || 0);
      if (gname.includes('gemini')) {
        if (bid.includes('weekly')) {
          el.geminiWeeklyBar.style.width = `${pct}%`;
          el.geminiWeeklyVal.textContent = `${pct}%`;
          if (b.time_until_reset) resetText = `Gemini Weekly: ${b.time_until_reset}`;
        } else if (bid.includes('5h')) {
          el.gemini5hBar.style.width = `${pct}%`;
          el.gemini5hVal.textContent = `${pct}%`;
        }
      }
    });
  });
  el.kpiQuotaReset.textContent = resetText;

  el.diagRpcInfo.textContent = JSON.stringify(data, null, 2);
}

async function fetchConversations() {
  const res = await fetch('/api/conversations');
  const data = await res.json();
  state.conversations = data;
  renderConversations();
}

async function fetchConversationDetails(cid) {
  const res = await fetch(`/api/conversations/${cid}`);
  const data = await res.json();
  state.timeline = data.timeline || [];
  const metrics = data.metrics || {};

  // Update KPIs
  el.kpiModel.textContent = metrics.primary_model || 'Gemini 3.8 Flash (High)';
  el.kpiPeakPrompt.textContent = (metrics.prompt_tokens_peak || 0).toLocaleString();

  const outToks = (metrics.cumulative_output_tokens || 0).toLocaleString();
  const thinkToks = (metrics.cumulative_thinking_tokens || 0).toLocaleString();
  el.kpiTokensRow.textContent = `${outToks}`;
  el.kpiThinkingSubtext.textContent = `+ ${thinkToks} reasoning tokens`;

  el.kpiTurns.textContent = `${metrics.planner_responses || 0} / ${metrics.total_steps || 0}`;
  el.kpiToolsSubtext.textContent = `${metrics.tool_calls_total || 0} tool calls executed`;

  renderTimeline();
}

async function fetchRequests() {
  const res = await fetch('/api/requests?limit=150');
  const data = await res.json();
  state.requests = data;
  renderRequests();
}

async function fetchAnalytics() {
  const res = await fetch('/api/analytics');
  const data = await res.json();
  state.analytics = data;
  if (state.activeTab === 'analytics') {
    renderCharts();
  }
}

// --- SSE LIVE STREAM ---
function initLiveStream() {
  const evtSource = new EventSource('/api/events/live');
  evtSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.active_conversation_id && data.active_conversation_id !== state.activeConversationId) {
        state.activeConversationId = data.active_conversation_id;
        fetchConversationDetails(state.activeConversationId);
      } else if (state.activeConversationId) {
        // Soft refresh timeline
        fetchConversationDetails(state.activeConversationId);
      }
      if (data.recent_requests) {
        state.requests = data.recent_requests;
        renderRequests();
      }
    } catch (e) {
      console.debug('SSE parse error:', e);
    }
  };
}

// --- RENDERING: TIMELINE WATERFALL ---
function renderTimeline() {
  const container = el.timelineContainer;
  container.innerHTML = '';

  let filtered = state.timeline.filter(item => {
    if (state.filterThinkingOnly && item.cycle_type !== 'agent_turn') return false;
    if (state.filterToolsOnly && (item.cycle_type !== 'agent_turn' || !item.tool_executions?.length)) return false;

    if (state.searchQuery) {
      const q = state.searchQuery;
      const text = JSON.stringify(item).toLowerCase();
      if (!text.includes(q)) return false;
    }
    return true;
  });

  el.timelineStats.textContent = `Showing ${filtered.length} of ${state.timeline.length} execution events`;

  filtered.forEach((item, idx) => {
    if (item.cycle_type === 'user_input') {
      const card = document.createElement('div');
      card.className = 'user-input-card';
      card.innerHTML = `
        <div class="user-input-header">User Prompt (Step ${item.step_index}) &bull; ${formatTime(item.timestamp)}</div>
        <div class="user-input-body">${escapeHtml(item.prompt)}</div>
      `;
      container.appendChild(card);
    } else if (item.cycle_type === 'agent_turn') {
      const card = document.createElement('div');
      card.className = 'timeline-turn-card';

      const toks = item.tokens || {};
      const tools = item.tool_calls_planned || [];
      const toolExecs = item.tool_executions || [];

      let toolsHtml = '';
      if (tools.length > 0) {
        toolsHtml = '<div class="turn-tools-list">';
        tools.forEach((t, tidx) => {
          const exec = toolExecs[tidx] || {};
          const statusClass = exec.status === 'ERROR' ? 'color: var(--accent-rose);' : 'color: var(--accent-emerald);';
          toolsHtml += `
            <div class="tool-item-pill" onclick="inspectTool(${idx}, ${tidx})">
              <div class="tool-left">
                <span class="tool-name">${escapeHtml(t.name)}</span>
                <span class="tool-args-snippet">${escapeHtml(JSON.stringify(t.args || {}))}</span>
              </div>
              <span class="mono-cell" style="${statusClass}">${exec.status || 'PLANNED'}</span>
            </div>
          `;
        });
        toolsHtml += '</div>';
      }

      card.innerHTML = `
        <div class="turn-header">
          <div class="turn-title-group">
            <span class="turn-num-pill">Step ${item.step_index}</span>
            <span class="turn-model-badge">${escapeHtml(item.model)}</span>
            <span class="badge badge-accent">Reasoning Turn</span>
          </div>
          <div class="turn-tokens-pill">
            In: ${toks.prompt?.toLocaleString()} | Out: ${toks.output?.toLocaleString()} | Think: ${toks.thinking?.toLocaleString()}
          </div>
        </div>

        ${item.thinking ? `
          <div class="turn-thinking-box" onclick="inspectThinking(${idx})">
            <div class="turn-thinking-header">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path></svg>
              Chain-of-Thought (${item.thinking_length} chars)
            </div>
            ${escapeHtml(item.thinking)}
          </div>
        ` : ''}

        ${toolsHtml}
      `;
      container.appendChild(card);
    }
  });
}

// --- RENDERING: REQUESTS TABLE ---
function renderRequests() {
  const tbody = el.requestsTableBody;
  tbody.innerHTML = '';

  let filtered = state.requests.filter(r => {
    if (state.searchQuery) {
      const q = state.searchQuery;
      return (
        r.trace_id?.toLowerCase().includes(q) ||
        r.response_id?.toLowerCase().includes(q) ||
        r.endpoint?.toLowerCase().includes(q) ||
        r.model?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  el.requestsCountBadge.textContent = `${filtered.length} requests`;

  filtered.forEach((r, idx) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="mono-cell">${escapeHtml(r.timestamp?.split(' ')[1] || r.timestamp || '')}</td>
      <td><strong>${escapeHtml(r.operation || r.endpoint)}</strong></td>
      <td><span class="badge ${r.is_streaming ? 'badge-accent' : ''}">${r.is_streaming ? 'SSE STREAM' : 'UNARY'}</span></td>
      <td class="mono-cell">${escapeHtml(r.trace_id?.substring(0, 14) || 'N/A')}...</td>
      <td class="mono-cell">${escapeHtml(r.response_id?.substring(0, 14) || 'N/A')}...</td>
      <td>${escapeHtml(r.model || 'Gemini 3.8 Flash')}</td>
      <td class="mono-cell">${(r.prompt_tokens || 0).toLocaleString()}</td>
      <td class="mono-cell">${(r.output_tokens || 0).toLocaleString()}</td>
      <td class="mono-cell">${(r.thinking_tokens || 0).toLocaleString()}</td>
      <td><span class="badge badge-success">${r.status || '200 OK'}</span></td>
      <td><button class="btn btn-secondary" onclick="inspectRequest(${idx})">Inspect</button></td>
    `;
    tbody.appendChild(tr);
  });
}

// --- RENDERING: CONVERSATIONS GRID ---
function renderConversations() {
  const grid = el.conversationsList;
  grid.innerHTML = '';

  state.conversations.forEach(c => {
    const card = document.createElement('div');
    card.className = `conv-card ${c.id === state.activeConversationId ? 'active-conv' : ''}`;
    card.onclick = () => {
      state.activeConversationId = c.id;
      renderConversations();
      fetchConversationDetails(c.id);
      document.querySelector('[data-tab="timeline"]').click();
    };

    card.innerHTML = `
      <div class="conv-title">${escapeHtml(c.title || c.id)}</div>
      <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">${escapeHtml(c.preview || 'No preview available')}</p>
      <div class="conv-meta-row">
        <span>Steps: ${c.step_count || 0}</span>
        <span>Peak Context: ${(c.prompt_tokens_peak || 0).toLocaleString()} tok</span>
      </div>
    `;
    grid.appendChild(card);
  });
}

// --- RENDERING: CHARTS ---
function renderCharts() {
  drawTokenGrowthChart();
  drawToolDistributionChart();
}

function drawTokenGrowthChart() {
  const canvas = document.getElementById('tokenGrowthChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  const turns = state.timeline.filter(c => c.cycle_type === 'agent_turn');
  if (turns.length === 0) {
    ctx.fillStyle = '#64748b';
    ctx.font = '12px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('No agent turns recorded yet', w / 2, h / 2);
    return;
  }

  const promptVals = turns.map(t => t.tokens?.prompt || 0);
  const outVals = turns.map(t => t.tokens?.output || 0);
  const thinkVals = turns.map(t => t.tokens?.thinking || 0);

  const maxVal = Math.max(...promptVals, 1000);
  const padding = 36;
  const plotW = w - padding * 2;
  const plotH = h - padding * 2;

  // Grid lines
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = padding + (plotH / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding, y);
    ctx.lineTo(w - padding, y);
    ctx.stroke();

    const valLabel = Math.round(maxVal * (1 - i / 4) / 1000) + 'k';
    ctx.fillStyle = '#64748b';
    ctx.font = '10px JetBrains Mono';
    ctx.textAlign = 'right';
    ctx.fillText(valLabel, padding - 6, y + 3);
  }

  // Draw series helper
  function drawLine(vals, color) {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    vals.forEach((v, i) => {
      const x = padding + (plotW / (vals.length - 1 || 1)) * i;
      const y = padding + plotH * (1 - v / maxVal);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  drawLine(promptVals, '#06b6d4');
  drawLine(outVals, '#8b5cf6');
  drawLine(thinkVals, '#f59e0b');
}

function drawToolDistributionChart() {
  const canvas = document.getElementById('toolDistributionChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);

  const w = rect.width;
  const h = rect.height;
  ctx.clearRect(0, 0, w, h);

  // Aggregate tool counts
  const counts = {};
  state.timeline.forEach(c => {
    (c.tool_calls_planned || []).forEach(t => {
      counts[t.name] = (counts[t.name] || 0) + 1;
    });
  });

  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (entries.length === 0) {
    ctx.fillStyle = '#64748b';
    ctx.font = '12px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('No tool invocations recorded yet', w / 2, h / 2);
    return;
  }

  const maxCount = Math.max(...entries.map(e => e[1]), 1);
  const barHeight = 22;
  const gap = 14;
  const startY = 24;

  entries.forEach(([name, cnt], i) => {
    const y = startY + (barHeight + gap) * i;
    const barW = (cnt / maxCount) * (w - 180);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '11px JetBrains Mono';
    ctx.textAlign = 'left';
    ctx.fillText(name, 10, y + 15);

    // Bar track
    ctx.fillStyle = '#1e2230';
    ctx.fillRect(120, y, w - 180, barHeight);

    // Fill
    ctx.fillStyle = '#6366f1';
    ctx.fillRect(120, y, barW, barHeight);

    ctx.fillStyle = '#f8fafc';
    ctx.font = '11px JetBrains Mono';
    ctx.textAlign = 'left';
    ctx.fillText(`${cnt}`, 130 + barW, y + 15);
  });
}

// --- INSPECTOR DRAWER ---
window.inspectThinking = function(timelineIdx) {
  const item = state.timeline[timelineIdx];
  if (!item) return;

  el.drawerBadge.textContent = `TURN ${item.step_index}`;
  el.drawerTitle.textContent = 'Chain-of-Thought Reasoning';
  el.drawerContent.innerHTML = `
    <div class="drawer-section">
      <div class="drawer-section-title">Model Configuration</div>
      <p style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-cyan);">${escapeHtml(item.model)}</p>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Token Distribution</div>
      <div class="conv-meta-row" style="margin-top: 0;">
        <span>Prompt: ${item.tokens?.prompt?.toLocaleString()}</span>
        <span>Output: ${item.tokens?.output?.toLocaleString()}</span>
        <span>Thinking: ${item.tokens?.thinking?.toLocaleString()}</span>
      </div>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Raw Reasoning Trace</div>
      <pre class="drawer-pre">${escapeHtml(item.thinking || 'No reasoning trace available')}</pre>
    </div>
  `;
  openDrawer();
};

window.inspectTool = function(timelineIdx, toolIdx) {
  const item = state.timeline[timelineIdx];
  if (!item) return;
  const tool = (item.tool_calls_planned || [])[toolIdx];
  const exec = (item.tool_executions || [])[toolIdx] || {};

  el.drawerBadge.textContent = 'TOOL INVOCATION';
  el.drawerTitle.textContent = tool?.name || 'Tool Details';
  el.drawerContent.innerHTML = `
    <div class="drawer-section">
      <div class="drawer-section-title">Tool Name & Status</div>
      <p style="font-family: var(--font-mono); font-size: 13px; color: var(--accent-indigo); font-weight: 600;">
        ${escapeHtml(tool?.name || 'unknown')} &bull; Status: ${escapeHtml(exec.status || 'DONE')}
      </p>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Input Parameters</div>
      <pre class="drawer-pre">${escapeHtml(JSON.stringify(tool?.args || {}, null, 2))}</pre>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Output Result</div>
      <pre class="drawer-pre">${escapeHtml(exec.output_preview || 'No captured stdout or output')}</pre>
    </div>
  `;
  openDrawer();
};

window.inspectRequest = function(reqIdx) {
  const req = state.requests[reqIdx];
  if (!req) return;

  el.drawerBadge.textContent = 'HTTP / SSE REQUEST';
  el.drawerTitle.textContent = req.operation || req.endpoint;
  el.drawerContent.innerHTML = `
    <div class="drawer-section">
      <div class="drawer-section-title">Endpoint & URL</div>
      <p style="font-family: var(--font-mono); font-size: 12px; color: var(--accent-cyan); word-break: break-all;">
        ${escapeHtml(req.url || req.endpoint)}
      </p>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Identifiers</div>
      <p style="font-family: var(--font-mono); font-size: 11px; margin-bottom: 4px;">Trace ID: ${escapeHtml(req.trace_id || 'N/A')}</p>
      <p style="font-family: var(--font-mono); font-size: 11px;">Response ID: ${escapeHtml(req.response_id || 'N/A')}</p>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Decoded Token Metrics</div>
      <div class="conv-meta-row" style="margin-top: 0;">
        <span>Prompt: ${req.prompt_tokens?.toLocaleString() || 0}</span>
        <span>Output: ${req.output_tokens?.toLocaleString() || 0}</span>
        <span>Reasoning: ${req.thinking_tokens?.toLocaleString() || 0}</span>
      </div>
    </div>
    <div class="drawer-section">
      <div class="drawer-section-title">Raw Request Object</div>
      <pre class="drawer-pre">${escapeHtml(JSON.stringify(req, null, 2))}</pre>
    </div>
  `;
  openDrawer();
};

function openDrawer() {
  el.inspectorDrawer.classList.remove('hidden');
}

function closeDrawer() {
  el.inspectorDrawer.classList.add('hidden');
}

// Helpers
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return isoStr;
  }
}

// Bootstrap
window.addEventListener('DOMContentLoaded', init);
