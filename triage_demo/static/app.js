const defaultSummary = {
  chiefComplaint: '待补充',
  duration: '待补充',
  accompanyingSymptoms: [],
  redFlags: [],
  recommendedDepartment: '待判断',
  triagePriority: '待判断',
  missingInformation: [],
  nextQuestion: '',
  doctorSummary: '患者信息尚未完善，等待对话开始。',
};

const initialAssistantMessage = '你好，我是门诊预问诊助手。请描述一下你目前最主要的不适症状，我会帮你整理就诊摘要。';

let messages = [{ role: 'assistant', content: initialAssistantMessage }];
let summary = { ...defaultSummary };
let loading = false;

const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const resetBtn = document.getElementById('resetBtn');
const copyBtn = document.getElementById('copyBtn');
const downloadBtn = document.getElementById('downloadBtn');
const modeSelect = document.getElementById('modeSelect');
const sampleButtons = document.querySelectorAll('.sample-btn');

const fields = {
  chiefComplaint: document.getElementById('chiefComplaint'),
  duration: document.getElementById('duration'),
  recommendedDepartment: document.getElementById('recommendedDepartment'),
  triagePriority: document.getElementById('triagePriority'),
  triageBadge: document.getElementById('triageBadge'),
  accompanyingSymptoms: document.getElementById('accompanyingSymptoms'),
  redFlags: document.getElementById('redFlags'),
  missingInformation: document.getElementById('missingInformation'),
  doctorSummary: document.getElementById('doctorSummary'),
};

function nowTime() {
  const date = new Date();
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
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
    bubble.innerHTML = `
      <div>${escapeHtml(message.content).replace(/\n/g, '<br>')}</div>
      <div class="message-meta">${message.role === 'assistant' ? 'AI 助手' : '患者'} · ${message.time || nowTime()}</div>
    `;
    chatWindow.appendChild(node);
  });

  if (loading) {
    const loadingRow = document.createElement('div');
    loadingRow.className = 'message-row assistant';
    loadingRow.innerHTML = `
      <div class="avatar">AI</div>
      <div class="bubble">
        <div class="loading-bubble">
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
          <span class="loading-dot"></span>
        </div>
        <div class="message-meta">AI 正在整理摘要...</div>
      </div>
    `;
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

function renderSummary() {
  fields.chiefComplaint.textContent = summary.chiefComplaint || '待补充';
  fields.duration.textContent = summary.duration || '待补充';
  fields.recommendedDepartment.textContent = summary.recommendedDepartment || '待判断';
  fields.triagePriority.textContent = summary.triagePriority || '待判断';
  fields.doctorSummary.textContent = summary.doctorSummary || '患者信息尚未完善，等待对话开始。';

  const badge = fields.triageBadge;
  badge.textContent = summary.triagePriority || '待判断';
  badge.className = 'triage-badge';
  if (summary.triagePriority === '普通') {
    badge.classList.add('normal');
  } else if (summary.triagePriority === '尽快') {
    badge.classList.add('warning');
  } else if (summary.triagePriority === '紧急') {
    badge.classList.add('danger');
  } else {
    badge.classList.add('neutral');
  }

  renderList(fields.accompanyingSymptoms, summary.accompanyingSymptoms, '待补充');
  renderList(fields.redFlags, summary.redFlags, '暂未识别');
  renderList(fields.missingInformation, summary.missingInformation, '无');
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
      body: JSON.stringify({
        mode: modeSelect.value,
        messages,
      }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || '请求失败');
    }

    summary = { ...defaultSummary, ...data.summary };
    pushMessage('assistant', data.reply || '我已帮你整理好摘要。');
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
    `推荐科室：${summary.recommendedDepartment || '待判断'}`,
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

function showToast(text) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 2400);
}

sendBtn.addEventListener('click', () => sendMessage());
resetBtn.addEventListener('click', resetConversation);
copyBtn.addEventListener('click', copySummary);
downloadBtn.addEventListener('click', downloadSummary);

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
