const STATUS_PALETTE = {
  escalated: 'danger',
  manual_review: 'warning',
  ready_for_booking: 'success',
  booked: 'neutral',
  in_review: 'info',
  new: 'info',
  closed: 'neutral',
};

const PRIORITY_PALETTE = {
  紧急: 'danger',
  尽快: 'warning',
  普通: 'info',
  待判断: 'neutral',
};

const REFRESH_INTERVAL_MS = 5000;
let activeStatus = '';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function formatConfidence(score) {
  const numeric = Number(score || 0);
  return `${Math.round(numeric * 100)}%`;
}

function formatUpdatedAt(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('zh-CN', { hour12: false });
}

function renderCaseRow(row) {
  const statusTone = STATUS_PALETTE[row.status] || 'info';
  const priorityTone = PRIORITY_PALETTE[row.triagePriority] || 'neutral';
  const redFlags = Array.isArray(row.redFlags) ? row.redFlags.filter(Boolean) : [];
  const missing = Array.isArray(row.missingInformation) ? row.missingInformation.filter(Boolean) : [];
  const needsReview = Boolean(row.needsManualReview);

  const redFlagChips = redFlags.length
    ? redFlags.slice(0, 4).map((flag) => `<span class="case-chip danger">${escapeHtml(flag)}</span>`).join('')
    : '<span class="case-chip neutral">暂无红旗征象</span>';

  const missingChips = missing.length
    ? missing.slice(0, 3).map((item) => `<span class="case-chip warning">${escapeHtml(item)}</span>`).join('')
    : '<span class="case-chip neutral">信息较完整</span>';

  const reviewBlock = needsReview
    ? `<div class="case-review-note">
         <span class="case-review-label">需人工复核</span>
         <span class="case-review-reason">${escapeHtml(row.reviewReason || '未提供原因')}</span>
       </div>`
    : '';

  const providerText = row.providerLabel || row.provider || '未知来源';

  return `
    <article class="case-row ${needsReview ? 'needs-review' : ''}" data-session="${escapeHtml(row.sessionId)}">
      <div class="case-row-head">
        <div class="case-row-left">
          <span class="triage-badge ${statusTone}">${escapeHtml(row.statusLabel)}</span>
          <span class="triage-badge ${priorityTone}">${escapeHtml(row.triagePriority)}</span>
          <span class="case-row-stage">${escapeHtml(row.workflowStageLabel || '')}</span>
        </div>
        <div class="case-row-meta">
          <span>会话 ${escapeHtml(row.sessionId)}</span>
          <span>· ${escapeHtml(row.turns || 0)} 轮</span>
          <span>· 置信度 ${formatConfidence(row.confidenceScore)}</span>
          <span>· ${escapeHtml(providerText)}</span>
        </div>
      </div>

      <div class="case-row-body">
        <div class="case-row-primary">
          <h3>${escapeHtml(row.chiefComplaint || '待补充')}</h3>
          <p class="case-row-department">建议科室：<strong>${escapeHtml(row.recommendedDepartment || '待判断')}</strong> · 生命周期：${escapeHtml(row.lifecycleState || '')}</p>
          ${reviewBlock}
        </div>
        <div class="case-row-side">
          <div class="case-row-chips">${redFlagChips}</div>
          <div class="case-row-chips">${missingChips}</div>
          <span class="case-row-updated">更新于 ${escapeHtml(formatUpdatedAt(row.updatedAt) || '-')}</span>
        </div>
      </div>

      <div class="case-row-actions">
        <a class="secondary-btn" href="/doctor?session=${encodeURIComponent(row.sessionId)}">打开单会话视图</a>
        <a class="secondary-btn" href="/patient?session=${encodeURIComponent(row.sessionId)}" target="_blank" rel="noopener">模拟患者端</a>
      </div>
    </article>
  `;
}

function renderQueue(data) {
  const listEl = document.getElementById('caseQueueList');
  const totalPill = document.getElementById('queueTotalPill');
  const cases = Array.isArray(data.cases) ? data.cases : [];

  if (totalPill) {
    const filterSuffix = activeStatus ? ` · 过滤：${activeStatus}` : '';
    totalPill.textContent = `会话总数：${cases.length}${filterSuffix}`;
  }

  if (!listEl) return;
  if (!cases.length) {
    listEl.innerHTML = '<div class="doctor-state-card">当前过滤条件下暂无案例。可尝试切换筛选或等待新会话加入。</div>';
    return;
  }
  listEl.innerHTML = cases.map(renderCaseRow).join('');
}

async function loadQueue() {
  const url = activeStatus ? `/api/cases?status=${encodeURIComponent(activeStatus)}` : '/api/cases';
  try {
    const response = await fetch(url, { headers: { 'Accept': 'application/json' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderQueue(data);
  } catch (err) {
    const listEl = document.getElementById('caseQueueList');
    if (listEl) {
      listEl.innerHTML = `<div class="doctor-state-card">加载案例失败：${escapeHtml(err.message || err)}</div>`;
    }
  }
}

function bindFilters() {
  const container = document.getElementById('queueStatusFilters');
  if (!container) return;
  container.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-status]');
    if (!button) return;
    container.querySelectorAll('button[data-status]').forEach((btn) => btn.classList.remove('is-active'));
    button.classList.add('is-active');
    activeStatus = button.dataset.status || '';
    loadQueue();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  bindFilters();
  loadQueue();
  setInterval(loadQueue, REFRESH_INTERVAL_MS);
});
