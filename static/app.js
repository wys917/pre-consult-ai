const defaultSummary = {
  chiefComplaint: '待补充',
  duration: '待补充',
  accompanyingSymptoms: [],
  redFlags: [],
  recommendedDepartment: '待判断',
  departmentReason: '待补充',
  triagePriority: '待判断',
  missingInformation: [],
  nextQuestion: '',
  doctorSummary: '患者信息尚未完善，等待对话开始。',
  pastHistory: [],
  allergyHistory: '待补充',
  medicationHistory: '待补充',
  consistencyAlerts: [],
};

const initialAssistantMessage = '你好，我是门诊预问诊助手。请描述一下你目前最主要的不适症状，我会帮你整理就诊摘要。';

let messages = [{ role: 'assistant', content: initialAssistantMessage }];
let summary = { ...defaultSummary };
let loading = false;
let emergencyShown = false;

const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const resetBtn = document.getElementById('resetBtn');
const copyBtn = document.getElementById('copyBtn');
const downloadBtn = document.getElementById('downloadBtn');
const pdfBtn = document.getElementById('pdfBtn');
const modeSelect = document.getElementById('modeSelect');
const sampleButtons = document.querySelectorAll('.sample-btn');
const registerBtn = document.getElementById('registerBtn');
const emergencyModal = document.getElementById('emergencyModal');
const emergencyCloseBtn = document.getElementById('emergencyCloseBtn');
const doctorModal = document.getElementById('doctorModal');
const doctorCloseBtn = document.getElementById('doctorCloseBtn');
const doctorModalTitle = document.getElementById('doctorModalTitle');
const doctorList = document.getElementById('doctorList');

const fields = {
  chiefComplaint: document.getElementById('chiefComplaint'),
  duration: document.getElementById('duration'),
  recommendedDepartment: document.getElementById('recommendedDepartment'),
  departmentReason: document.getElementById('departmentReason'),
  triagePriority: document.getElementById('triagePriority'),
  triageBadge: document.getElementById('triageBadge'),
  accompanyingSymptoms: document.getElementById('accompanyingSymptoms'),
  redFlags: document.getElementById('redFlags'),
  missingInformation: document.getElementById('missingInformation'),
  doctorSummary: document.getElementById('doctorSummary'),
  pastHistory: document.getElementById('pastHistory'),
  allergyHistory: document.getElementById('allergyHistory'),
  medicationHistory: document.getElementById('medicationHistory'),
  consistencyAlerts: document.getElementById('consistencyAlerts'),
};

function nowTime() {
  const date = new Date();
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function quickReplyCandidates(item) {
  const map = {
    年龄: ['我32岁。', '我45岁。'],
    症状持续时间: ['症状持续两天了。', '大概一周了。'],
    最高体温: ['最高体温38.5度。', '最高39.2度。'],
    '是否伴呼吸困难/大汗/放射痛': ['有呼吸困难和出汗。', '没有呼吸困难，也没有放射痛。'],
    腹痛部位: ['主要是右下腹痛。', '上腹部隐痛。'],
    是否咳痰或气短: ['有黄痰，也有点气短。', '没有痰，也不气短。'],
    '是否伴视物模糊/麻木/呕吐': ['有恶心呕吐。', '没有视物模糊和麻木。'],
  };
  return map[item] || [];
}

function renderMessages() {
  chatWindow.innerHTML = '';
  messages.forEach((message) => {
    const template = document.getElementById('messageTemplate');
    const node = template.content.cloneNode(true);
    const row = node.querySelector('.message-row');
    const avatar = node.querySelector('.avatar');
    const bubble = node.querySelector('.bubble');
    row.classList.add(message.role);
    avatar.textContent = message.role === 'assistant' ? 'AI' : '患';
    bubble.innerHTML = `<div>${escapeHtml(message.content).replace(/\n/g, '<br>')}</div><div class="message-meta">${message.role === 'assistant' ? 'AI 助手' : '患者'} · ${message.time || nowTime()}</div>`;
    chatWindow.appendChild(node);
  });

  if (loading) {
    const loadingRow = document.createElement('div');
    loadingRow.className = 'message-row assistant';
    loadingRow.innerHTML = `<div class="avatar">AI</div><div class="bubble"><div class="loading-bubble"><span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span></div><div class="message-meta">AI 正在整理摘要...</div></div>`;
    chatWindow.appendChild(loadingRow);
  }
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function renderList(element, items, emptyText) {
  element.innerHTML = '';
  const list = items && items.length ? items : [emptyText];
  list.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    element.appendChild(li);
  });
  element.classList.toggle('empty-list', !(items && items.length));
}

function renderMissingList(items) {
  fields.missingInformation.innerHTML = '';
  if (!(items && items.length)) {
    renderList(fields.missingInformation, [], '无');
    return;
  }

  items.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'missing-item';

    const textSpan = document.createElement('span');
    textSpan.textContent = item;
    li.appendChild(textSpan);

    const actions = document.createElement('div');
    actions.className = 'missing-actions';

    quickReplyCandidates(item).forEach((candidate) => {
      const btn = document.createElement('button');
      btn.className = 'quick-fill-btn';
      btn.textContent = candidate;
      btn.addEventListener('click', () => sendMessage(candidate));
      actions.appendChild(btn);
    });

    if (actions.children.length) li.appendChild(actions);
    fields.missingInformation.appendChild(li);
  });
  fields.missingInformation.classList.remove('empty-list');
}

function renderSummary() {
  fields.chiefComplaint.textContent = summary.chiefComplaint || '待补充';
  fields.duration.textContent = summary.duration || '待补充';
  fields.recommendedDepartment.textContent = summary.recommendedDepartment || '待判断';
  fields.departmentReason.textContent = summary.departmentReason || '待补充';
  fields.triagePriority.textContent = summary.triagePriority || '待判断';
  fields.doctorSummary.textContent = summary.doctorSummary || '患者信息尚未完善，等待对话开始。';
  fields.allergyHistory.textContent = summary.allergyHistory || '待补充';
  fields.medicationHistory.textContent = summary.medicationHistory || '待补充';

  const badge = fields.triageBadge;
  badge.textContent = summary.triagePriority || '待判断';
  badge.className = 'triage-badge';
  if (summary.triagePriority === '普通') badge.classList.add('normal');
  else if (summary.triagePriority === '尽快') badge.classList.add('warning');
  else if (summary.triagePriority === '紧急') badge.classList.add('danger');
  else badge.classList.add('neutral');

  renderList(fields.accompanyingSymptoms, summary.accompanyingSymptoms, '待补充');
  renderList(fields.redFlags, summary.redFlags, '暂未识别');
  renderList(fields.pastHistory, summary.pastHistory, '待补充');
  renderList(fields.consistencyAlerts, summary.consistencyAlerts, '暂无');
  renderMissingList(summary.missingInformation);

  const hasDepartment = hasConfirmedDepartment(summary.recommendedDepartment);
  registerBtn.hidden = !hasDepartment;
}

function normalizeDepartment(value) {
  return String(value || '').trim();
}

function hasConfirmedDepartment(value) {
  const department = normalizeDepartment(value);
  return Boolean(department) && department !== '待判断' && department !== '待补充';
}

function pushMessage(role, content) {
  messages.push({ role, content, time: nowTime() });
}

async function sendMessage(text) {
  const content = (text || messageInput.value || '').trim();
  if (!content || loading) return;

  pushMessage('user', content);
  messageInput.value = '';
  loading = true;
  sendBtn.disabled = true;
  renderMessages();

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: modeSelect.value, messages }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败');

    summary = { ...defaultSummary, ...data.summary };
    pushMessage('assistant', data.reply || '我已帮你整理好摘要。');

    if (summary.triagePriority === '紧急' && !emergencyShown) {
      emergencyShown = true;
      openModal(emergencyModal);
    }

    if (data.source === 'api') showToast(`本轮来源：DeepSeek API (${data.model || 'unknown'})`);
    else if (data.source === 'mock') showToast('本轮来源：Mock 规则引擎');
  } catch (error) {
    pushMessage('assistant', `当前请求没有成功：${error.message}`);
    showToast(error.message);
  } finally {
    loading = false;
    sendBtn.disabled = false;
    renderMessages();
    renderSummary();
    messageInput.focus();
  }
}

function resetConversation() {
  messages = [{ role: 'assistant', content: initialAssistantMessage, time: nowTime() }];
  summary = { ...defaultSummary };
  loading = false;
  emergencyShown = false;
  closeModal(emergencyModal);
  closeModal(doctorModal);
  renderMessages();
  renderSummary();
  messageInput.value = '';
  messageInput.focus();
}

function buildSummaryText() {
  const formatList = (items, emptyText) => (items && items.length ? items.join('、') : emptyText);
  return [
    '【结构化病历摘要】',
    `主诉：${summary.chiefComplaint || '待补充'}`,
    `症状持续时间：${summary.duration || '待补充'}`,
    `伴随症状：${formatList(summary.accompanyingSymptoms, '待补充')}`,
    `红旗征象：${formatList(summary.redFlags, '暂未识别')}`,
    `信息一致性提醒：${formatList(summary.consistencyAlerts, '暂无')}`,
    `既往史：${formatList(summary.pastHistory, '待补充')}`,
    `过敏史：${summary.allergyHistory || '待补充'}`,
    `近期用药史：${summary.medicationHistory || '待补充'}`,
    `推荐科室：${summary.recommendedDepartment || '待判断'}`,
    `科室推荐原因：${summary.departmentReason || '待补充'}`,
    `就诊优先级：${summary.triagePriority || '待判断'}`,
    `仍待补充信息：${formatList(summary.missingInformation, '无')}`,
    '',
    '【医生端摘要】',
    summary.doctorSummary || '患者信息尚未完善，等待对话开始。',
  ].join('\n');
}

async function copySummary() {
  try {
    await navigator.clipboard.writeText(buildSummaryText());
    showToast('已复制到剪贴板');
  } catch (error) {
    showToast('复制失败，请手动复制');
  }
}

function downloadSummary() {
  const blob = new Blob([JSON.stringify(summary, null, 2)], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'triage-summary.json';
  link.click();
  URL.revokeObjectURL(url);
}

function exportSummaryPdf() {
  const content = buildSummaryText().replace(/\n/g, '<br>');
  const win = window.open('', '_blank');
  if (!win) {
    showToast('无法打开打印窗口，请检查浏览器设置');
    return;
  }
  win.document.write(`<html><head><title>预问诊单</title><style>body{font-family:Arial,"Microsoft YaHei";padding:28px;line-height:1.7;color:#222}</style></head><body><h2>门诊预问诊单</h2><div>${content}</div></body></html>`);
  win.document.close();
  win.focus();
  setTimeout(() => win.print(), 250);
}

function openModal(el) {
  el.hidden = false;
}

function closeModal(el) {
  el.hidden = true;
}

async function openDoctorPanel() {
  const department = summary.recommendedDepartment;
  if (!department || department === '待判断') {
    showToast('请先完成分诊再挂号');
    return;
  }
  try {
    doctorModalTitle.textContent = `${department} · 当日坐诊医生`;
    doctorList.innerHTML = '<p>正在加载医生信息...</p>';
    openModal(doctorModal);

    const res = await fetch(`/api/departments/${encodeURIComponent(department)}/doctors`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '加载医生列表失败');

    doctorList.innerHTML = '';
    data.doctors.forEach((doctor) => {
      const card = document.createElement('article');
      card.className = 'doctor-item';
      card.innerHTML = `
        <div>
          <h4>${doctor.name} · ${doctor.title}</h4>
          <p>${doctor.intro}</p>
          <p class="slots">剩余名额：${doctor.slots}</p>
        </div>
        <button class="primary-btn doctor-register-btn" ${doctor.slots <= 0 ? 'disabled' : ''}>挂号</button>
      `;
      card.querySelector('.doctor-register-btn').addEventListener('click', (event) => registerDoctor(event, department, doctor.id));
      doctorList.appendChild(card);
    });
  } catch (error) {
    doctorList.innerHTML = `<p>${error.message}</p>`;
  }
}

async function registerDoctor(event, department, doctorId) {
  const btn = event.currentTarget;
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = '挂号中...';
  try {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const res = await fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ department, doctorId, patientName: '演示患者' }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '挂号失败');

    showToast(`✅ ${data.message}`);
    btn.textContent = '挂号成功';
    btn.classList.add('success-btn');
    openSuccessBanner(data);
    await openDoctorPanel();
  } catch (error) {
    showToast(error.message);
    btn.disabled = false;
    btn.textContent = old;
  }
}

function openSuccessBanner(data) {
  const toast = document.createElement('div');
  toast.className = 'success-banner';
  toast.innerHTML = `<strong>挂号成功</strong><div>${data.appointmentId} · ${data.department} · ${data.doctor.name}</div>`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

function showToast(text) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2400);
}

sendBtn.addEventListener('click', () => sendMessage());
resetBtn.addEventListener('click', resetConversation);
copyBtn.addEventListener('click', copySummary);
downloadBtn.addEventListener('click', downloadSummary);
pdfBtn.addEventListener('click', exportSummaryPdf);
registerBtn.addEventListener('click', openDoctorPanel);
emergencyCloseBtn.addEventListener('click', () => closeModal(emergencyModal));
doctorCloseBtn.addEventListener('click', () => closeModal(doctorModal));

messageInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

sampleButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const sample = button.dataset.message || '';
    sendMessage(sample);
  });
});

modeSelect.addEventListener('change', () => {
  showToast(modeSelect.value === 'mock' ? '已切换到 Mock 演示模式' : '已切换到 API 模式，请先配置后端接口');
});

resetConversation();
