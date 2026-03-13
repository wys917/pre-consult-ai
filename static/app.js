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
  imageFindings: '未提供影像',
  departmentProfile: {},
};

const providerLabels = {
  doubao: '豆包',
  deepseek: 'DeepSeek',
  mock: 'Mock 规则引擎',
};

const initialAssistantMessage = '你好，我是门诊预问诊助手。请描述一下你目前最主要的不适症状，我会帮你整理就诊摘要。';

let messages = [{ role: 'assistant', content: initialAssistantMessage }];
let summary = { ...defaultSummary };
let loading = false;
let emergencyShown = false;
let activeDoctorDepartment = '';
let activeDoctorDate = '';
let departmentCatalog = [];

const chatWindow = document.getElementById('chatWindow');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const resetBtn = document.getElementById('resetBtn');
const copyBtn = document.getElementById('copyBtn');
const downloadBtn = document.getElementById('downloadBtn');
const pdfBtn = document.getElementById('pdfBtn');
const providerSelect = document.getElementById('providerSelect');
const providerStatus = document.getElementById('providerStatus');
const imageInput = document.getElementById('imageInput');
const uploadBtn = document.getElementById('uploadBtn');
const imagePreviewContainer = document.getElementById('imagePreviewContainer');
const imagePreview = document.getElementById('imagePreview');
const clearImageBtn = document.getElementById('clearImageBtn');
const sampleButtons = document.querySelectorAll('.sample-btn');
const registerBtn = document.getElementById('registerBtn');
const emergencyModal = document.getElementById('emergencyModal');
const emergencyCloseBtn = document.getElementById('emergencyCloseBtn');
const bookingModal = document.getElementById('bookingModal');
const bookingCloseBtn = document.getElementById('bookingCloseBtn');
const bookingModalTitle = document.getElementById('bookingModalTitle');
const bookingModalHint = document.getElementById('bookingModalHint');
const departmentPicker = document.getElementById('departmentPicker');
const doctorList = document.getElementById('doctorList');
const summaryScroll = document.getElementById('summaryScroll');

const bookingPriority = document.getElementById('bookingPriority');
const bookingDate = document.getElementById('bookingDate');
const bookingHint = document.getElementById('bookingHint');
const departmentOverview = document.getElementById('departmentOverview');
const departmentLocation = document.getElementById('departmentLocation');
const departmentWaitTime = document.getElementById('departmentWaitTime');
const departmentTag = document.getElementById('departmentTag');
const departmentServices = document.getElementById('departmentServices');
const departmentTips = document.getElementById('departmentTips');

const fields = {
  consistencyAlerts: document.getElementById('consistencyAlerts'),
  imageFindings: document.getElementById('imageFindings'),
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
};

function nowTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function todayLabel() {
  return new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function fileStamp() {
  const date = new Date();
  const parts = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
    String(date.getHours()).padStart(2, '0'),
    String(date.getMinutes()).padStart(2, '0'),
  ];
  return `${parts[0]}${parts[1]}${parts[2]}-${parts[3]}${parts[4]}`;
}

function escapeHtml(text) {
  return String(text)
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
    '是否咳痰或气短': ['有黄痰，也有点气短。', '没有痰，也不气短。'],
    '是否伴视物模糊/麻木/呕吐': ['有恶心呕吐。', '没有视物模糊和麻木。'],
  };
  return map[item] || [];
}

function normalizeDepartment(value) {
  return String(value || '').trim();
}

function hasConfirmedDepartment(value) {
  const department = normalizeDepartment(value);
  return Boolean(department) && department !== '待判断' && department !== '待补充';
}

function pushMessage(role, content, apiContent = null) {
  messages.push({
    role,
    content,
    apiContent: apiContent !== null ? apiContent : content,
    time: nowTime(),
  });
}

function setProviderStatus() {
  const provider = providerSelect.value;
  const text = {
    doubao: '当前使用豆包通道，适合演示实时摘要与影像上传。',
    deepseek: '当前使用 DeepSeek 通道，适合文本问诊与结构化输出。',
    mock: '当前使用 Mock 规则引擎，无需联网即可演示。',
  }[provider] || '当前使用智能整理模式。';
  providerStatus.textContent = text;
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

function renderDepartmentProfile(profile, department) {
  const hasDepartment = hasConfirmedDepartment(department);
  const safeProfile = profile && typeof profile === 'object' ? profile : {};
  const location = safeProfile.location || '门诊分诊台';

  departmentOverview.textContent = hasDepartment
    ? safeProfile.overview || `建议先前往${department}完成专科评估。`
    : '完成分诊后，将展示推荐科室的接诊范围与就诊提示。';
  departmentLocation.textContent = hasDepartment ? location : '门诊分诊台';
  departmentTag.textContent = hasDepartment ? department : '待判断';
  departmentWaitTime.textContent = hasDepartment ? safeProfile.waitTime || '以现场为准' : '--';
  renderList(departmentServices, hasDepartment ? safeProfile.services : [], '等待分诊结果');
  renderList(departmentTips, hasDepartment ? safeProfile.tips : [], '完成分诊后更新');
}

function renderDepartmentPicker() {
  departmentPicker.innerHTML = '';
  if (!departmentCatalog.length) {
    departmentPicker.innerHTML = '<div class="doctor-state-card">暂无诊室数据</div>';
    return;
  }

  departmentCatalog.forEach((department) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `department-pick-card${department.name === activeDoctorDepartment ? ' active' : ''}`;
    button.innerHTML = `
      <strong>${escapeHtml(department.name)}</strong>
      <span>${escapeHtml(department.location || '门诊分诊台')}</span>
      <small>${department.doctorCount || 0} 位医生</small>
    `;
    button.addEventListener('click', () => openBookingWorkspace(department.name));
    departmentPicker.appendChild(button);
  });
}

function resetDoctorList(message = '点击左侧诊室卡片查看当日可挂医生。') {
  doctorList.innerHTML = `<div class="doctor-state-card">${escapeHtml(message)}</div>`;
}

function renderDoctorAvailability(doctors, date, department) {
  if (!doctors || !doctors.length) {
    resetDoctorList('当前没有可展示的号源信息。');
    return;
  }

  doctorList.innerHTML = '';
  doctors.forEach((doctor) => {
    const card = document.createElement('article');
    card.className = 'doctor-item';
    card.innerHTML = `
      <div class="doctor-main">
        <div class="doctor-topline">
          <h4>${escapeHtml(doctor.name)} <span>${escapeHtml(doctor.title)}</span></h4>
          <span class="doctor-fee">${Number(doctor.fee || 0) === 0 ? '免费' : `￥${doctor.fee}`}</span>
        </div>
        <p class="doctor-intro">${escapeHtml(doctor.intro || '暂无简介')}</p>
        <div class="doctor-tags">
          <span>${escapeHtml(doctor.specialty || department)}</span>
          <span>${escapeHtml(doctor.location || '门诊楼')}</span>
        </div>
      </div>
      <div class="doctor-side">
        <div class="doctor-meta-grid">
          <div>
            <span>时间</span>
            <strong>${escapeHtml(doctor.schedule || '全天')}</strong>
          </div>
          <div>
            <span>剩余名额</span>
            <strong>${doctor.slots}</strong>
          </div>
          <div>
            <span>日期</span>
            <strong>${escapeHtml(date || todayLabel())}</strong>
          </div>
        </div>
        <button class="primary-btn doctor-register-btn" ${doctor.slots <= 0 ? 'disabled' : ''}>${doctor.slots <= 0 ? '已满' : '立即挂号'}</button>
      </div>
    `;

    const actionBtn = card.querySelector('.doctor-register-btn');
    actionBtn.addEventListener('click', (event) => registerDoctor(event, department, doctor.id));
    doctorList.appendChild(card);
  });
}

function updateBookingPanel() {
  const department = summary.recommendedDepartment || '待判断';
  const priority = summary.triagePriority || '待判断';
  const hasDepartment = hasConfirmedDepartment(department);

  bookingPriority.textContent = priority;
  bookingDate.textContent = activeDoctorDate || '--';
  bookingHint.textContent = hasDepartment
    ? `系统建议优先前往 ${department}，点击按钮进入挂号工作台查看详细科室信息与号源。`
    : '完成分诊后，可点击按钮进入挂号工作台。';

  registerBtn.disabled = !hasDepartment;
  registerBtn.textContent = hasDepartment ? '查看科室与挂号' : '等待分诊结果';

  if (!hasDepartment) {
    activeDoctorDepartment = '';
    activeDoctorDate = '';
    bookingDate.textContent = '--';
  }
}

function renderSummary() {
  fields.imageFindings.textContent = summary.imageFindings || '未提供影像';
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
  updateBookingPanel();
}

async function sendMessage(text) {
  const content = (text || messageInput.value || '').trim();
  const file = imageInput.files[0];

  if (!content && !file) return;
  if (loading) return;

  let apiContent = content;
  if (file) {
    const base64Image = await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (event) => resolve(event.target.result);
      reader.readAsDataURL(file);
    });
    apiContent = [
      { type: 'text', text: content || '请分析这张图片。' },
      { type: 'image_url', image_url: { url: base64Image } },
    ];
  }

  let displayMessage = content;
  if (file) displayMessage += '\n[已上传图片]';

  pushMessage('user', displayMessage, apiContent);
  messageInput.value = '';
  loading = true;
  sendBtn.disabled = true;
  renderMessages();

  try {
    const apiMessages = messages.map((message) => ({
      role: message.role,
      content: message.apiContent || message.content,
    }));

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: providerSelect.value,
        messages: apiMessages,
      }),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '请求失败');

    summary = { ...defaultSummary, ...data.summary };
    pushMessage('assistant', data.reply || '我已帮你整理好摘要。');
    clearImageSelection();

    if (summary.triagePriority === '紧急' && !emergencyShown) {
      emergencyShown = true;
      openModal(emergencyModal);
    }

    const sourceText = data.source === 'mock'
      ? 'Mock 规则引擎'
      : `${data.providerLabel || providerLabels[data.provider] || 'API'} (${data.model || 'unknown'})`;
    showToast(`本轮来源：${sourceText}`);
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

function clearImageSelection() {
  imageInput.value = '';
  imagePreview.src = '';
  imagePreviewContainer.hidden = true;
}

function resetConversation() {
  messages = [{ role: 'assistant', content: initialAssistantMessage, time: nowTime() }];
  summary = { ...defaultSummary };
  loading = false;
  emergencyShown = false;
  activeDoctorDepartment = '';
  activeDoctorDate = '';
  closeModal(emergencyModal);
  closeModal(bookingModal);
  resetDoctorList();
  renderMessages();
  renderSummary();
  clearImageSelection();
  messageInput.value = '';
  messageInput.focus();
}

function buildSummaryText() {
  const formatList = (items, emptyText) => (items && items.length ? items.join('、') : emptyText);
  return [
    '【结构化病历摘要】',
    `导出时间：${new Date().toLocaleString('zh-CN')}`,
    `主诉：${summary.chiefComplaint || '待补充'}`,
    `症状持续时间：${summary.duration || '待补充'}`,
    `伴随症状：${formatList(summary.accompanyingSymptoms, '待补充')}`,
    `红旗征象：${formatList(summary.redFlags, '暂未识别')}`,
    `影像/检查所见：${summary.imageFindings || '未提供影像'}`,
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

function fallbackCopyText(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  textarea.style.pointerEvents = 'none';
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  let copied = false;
  try {
    copied = document.execCommand('copy');
  } catch (error) {
    copied = false;
  }
  textarea.remove();
  return copied;
}

async function copySummary() {
  const text = buildSummaryText();

  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else if (!fallbackCopyText(text)) {
      throw new Error('浏览器复制权限不可用');
    }
    showToast('已复制到剪贴板');
  } catch (error) {
    if (fallbackCopyText(text)) {
      showToast('已复制到剪贴板');
      return;
    }
    showToast('复制失败，请检查浏览器权限');
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function downloadSummary() {
  const payload = {
    exportedAt: new Date().toISOString(),
    provider: providerSelect.value,
    providerLabel: providerLabels[providerSelect.value],
    summary,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
  downloadBlob(blob, `triage-summary-${fileStamp()}.json`);
  showToast('JSON 已开始下载');
}

function fallbackPrintPdf() {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.width = '0';
  iframe.style.height = '0';
  iframe.style.border = '0';
  iframe.style.opacity = '0';
  document.body.appendChild(iframe);

  const doc = iframe.contentWindow.document;
  const content = escapeHtml(buildSummaryText()).replace(/\n/g, '<br>');
  doc.open();
  doc.write(`
    <html lang="zh-CN">
      <head>
        <title>预问诊单</title>
        <style>
          body { font-family: "PingFang SC", "Microsoft YaHei", sans-serif; padding: 28px; line-height: 1.8; color: #1b2435; }
          h1 { font-size: 22px; margin-bottom: 18px; }
        </style>
      </head>
      <body>
        <h1>门诊预问诊单</h1>
        <div>${content}</div>
      </body>
    </html>
  `);
  doc.close();

  iframe.onload = () => {
    iframe.contentWindow.focus();
    iframe.contentWindow.print();
    setTimeout(() => iframe.remove(), 1500);
  };
}

async function exportSummaryPdf() {
  const originalText = pdfBtn.textContent;
  pdfBtn.disabled = true;
  pdfBtn.textContent = '生成中...';

  try {
    const response = await fetch('/api/export/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ summary }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || 'PDF 导出失败');
    }

    const blob = await response.blob();
    downloadBlob(blob, `triage-summary-${fileStamp()}.pdf`);
    showToast('PDF 已开始下载');
  } catch (error) {
    showToast(`${error.message}，已切换浏览器打印`);
    fallbackPrintPdf();
  } finally {
    pdfBtn.disabled = false;
    pdfBtn.textContent = originalText;
  }
}

function openModal(element) {
  element.hidden = false;
}

function closeModal(element) {
  element.hidden = true;
}

async function ensureDepartmentCatalog() {
  if (departmentCatalog.length) return;
  const response = await fetch('/api/departments');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '加载诊室列表失败');
  departmentCatalog = data.departments || [];
}

async function loadDoctorAvailability({ silent = false } = {}) {
  const department = activeDoctorDepartment || summary.recommendedDepartment;
  if (!hasConfirmedDepartment(department)) {
    showToast('请先完成分诊再挂号');
    return;
  }

  doctorList.innerHTML = '<div class="doctor-state-card">正在加载当日医生号源...</div>';

  try {
    const response = await fetch(`/api/departments/${encodeURIComponent(department)}/doctors`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '加载医生列表失败');

    activeDoctorDepartment = department;
    activeDoctorDate = data.date || todayLabel();
    if (data.departmentProfile) {
      summary = { ...summary, departmentProfile: data.departmentProfile };
      renderDepartmentProfile(summary.departmentProfile, department);
    }
    bookingDate.textContent = activeDoctorDate;
    bookingModalTitle.textContent = `${department} · 推荐科室与当日号源`;
    bookingModalHint.textContent = `当前展示 ${department} 的接诊信息与当日可挂医生，你也可以切换左侧其他诊室。`;
    renderDoctorAvailability(data.doctors, activeDoctorDate, department);
    renderDepartmentPicker();

    if (!silent) {
      showToast(`${department} 当日号源已更新`);
    }
  } catch (error) {
    resetDoctorList(error.message);
    showToast(error.message);
  } finally {
    updateBookingPanel();
  }
}

async function openBookingWorkspace(preferredDepartment = '') {
  const targetDepartment = preferredDepartment || summary.recommendedDepartment;
  if (!hasConfirmedDepartment(targetDepartment)) {
    showToast('请先完成分诊再进入挂号界面');
    return;
  }

  try {
    await ensureDepartmentCatalog();
    activeDoctorDepartment = targetDepartment;
    bookingPriority.textContent = summary.triagePriority || '待判断';
    bookingHint.textContent = `系统建议优先前往 ${targetDepartment}，你也可以切换查看其他诊室。`;
    openModal(bookingModal);
    renderDepartmentPicker();
    await loadDoctorAvailability({ silent: true });
  } catch (error) {
    showToast(error.message);
  }
}

async function registerDoctor(event, department, doctorId) {
  const btn = event.currentTarget;
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = '挂号中...';

  try {
    const response = await fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        department,
        doctorId,
        patientName: '演示患者',
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '挂号失败');

    btn.textContent = '挂号成功';
    btn.classList.add('success-btn');
    openSuccessBanner(data);
    await loadDoctorAvailability({ silent: true });
  } catch (error) {
    btn.disabled = false;
    btn.textContent = originalText;
    showToast(error.message);
  }
}

function openSuccessBanner(data) {
  document.querySelectorAll('.success-banner').forEach((node) => node.remove());
  const toast = document.createElement('div');
  toast.className = 'success-banner';
  toast.innerHTML = `
    <strong>挂号成功</strong>
    <div>${escapeHtml(data.appointmentId)} · ${escapeHtml(data.department)} · ${escapeHtml(data.doctor.name)}</div>
    <div>${escapeHtml(data.message)}</div>
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
}

function showToast(text) {
  document.querySelectorAll('.toast').forEach((node) => node.remove());
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2400);
}

function lockWheelToContainer(container) {
  container.addEventListener(
    'wheel',
    (event) => {
      if (window.innerWidth <= 1180) return;
      if (container.scrollHeight <= container.clientHeight) return;
      event.preventDefault();
      container.scrollTop += event.deltaY;
    },
    { passive: false },
  );
}

uploadBtn.addEventListener('click', () => imageInput.click());

imageInput.addEventListener('change', () => {
  if (imageInput.files && imageInput.files[0]) {
    imagePreview.src = URL.createObjectURL(imageInput.files[0]);
    imagePreviewContainer.hidden = false;
    if (providerSelect.value === 'deepseek') {
      showToast('DeepSeek 当前按文本模式处理，若需要看图可切换到豆包。');
    }
  }
});

clearImageBtn.addEventListener('click', clearImageSelection);
sendBtn.addEventListener('click', () => sendMessage());
resetBtn.addEventListener('click', resetConversation);
copyBtn.addEventListener('click', copySummary);
downloadBtn.addEventListener('click', downloadSummary);
pdfBtn.addEventListener('click', exportSummaryPdf);
registerBtn.addEventListener('click', () => openBookingWorkspace());
emergencyCloseBtn.addEventListener('click', () => closeModal(emergencyModal));
bookingCloseBtn.addEventListener('click', () => closeModal(bookingModal));

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

providerSelect.addEventListener('change', () => {
  setProviderStatus();
  showToast(`已切换到 ${providerLabels[providerSelect.value] || '新模型'} 通道`);
});

lockWheelToContainer(summaryScroll);
setProviderStatus();
resetConversation();
