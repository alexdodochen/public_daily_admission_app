// ========================================================================
// Small vanilla JS app. No framework — keeps the local bundle zero-deps.
// ========================================================================

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(url, { method = 'GET', body = null } = {}) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({ ok: false, detail: 'bad json' }));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

function flash(el, msg, kind = 'ok') {
  if (!el) return;
  el.textContent = msg;
  el.className = 'msg ' + kind;
  setTimeout(() => { if (el.textContent === msg) el.textContent = ''; }, 5000);
}

// ============================ settings page ============================

if (document.getElementById('settings-form')) {
  const PROVIDER_HELP = {
    anthropic: 'Claude API key 取得：https://console.anthropic.com/ → API Keys',
    openai:    'OpenAI API key 取得：https://platform.openai.com/api-keys',
    gemini:    'Gemini API key 取得（免費 tier 可用）：https://aistudio.google.com/app/apikey',
  };
  const sel = $('#llm_provider');
  const help = $('#provider-help');
  const updateHelp = () => { help.textContent = PROVIDER_HELP[sel.value] || ''; };
  sel.addEventListener('change', updateHelp);
  updateHelp();

  $('#settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api('/api/settings', { method: 'POST', body: fd });
      flash($('#save-msg'), '✓ 已儲存', 'ok');
    } catch (err) {
      flash($('#save-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#test-btn').addEventListener('click', async () => {
    $('#test-output').textContent = '測試中…';
    try {
      const r = await api('/api/settings/test');
      $('#test-output').textContent = JSON.stringify(r, null, 2);
    } catch (err) {
      $('#test-output').textContent = err.message;
    }
  });
}

// ============================ workflow page ============================

if (document.querySelector('.stepper')) {
  // step switcher
  $$('.step').forEach(s => s.addEventListener('click', () => {
    $$('.step').forEach(x => x.classList.remove('active'));
    s.classList.add('active');
    const i = s.dataset.step;
    $$('.panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== i));
  }));

  // default date = today (Taipei), format YYYYMMDD
  const now = new Date();
  const tp = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000);
  const y = tp.getFullYear();
  const m = String(tp.getMonth() + 1).padStart(2, '0');
  const d = String(tp.getDate()).padStart(2, '0');
  $('#date-input').value = `${y}${m}${d}`;

  setupStep1();
  setupStep2();
  setupStep3();
  setupStep4();
}

// ---------- Step 1: OCR ----------
let ocrRows = [];

function setupStep1() {
  const dz = $('#drop-zone');
  const fi = $('#file-input');
  const preview = $('#preview');
  let currentFile = null;

  const showFile = (f) => {
    currentFile = f;
    const reader = new FileReader();
    reader.onload = (e) => { preview.src = e.target.result; preview.style.display = 'block'; };
    reader.readAsDataURL(f);
    $('#ocr-btn').disabled = false;
  };

  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('active'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('active'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault(); dz.classList.remove('active');
    const f = e.dataTransfer.files[0];
    if (f) showFile(f);
  });
  fi.addEventListener('change', () => { if (fi.files[0]) showFile(fi.files[0]); });
  // Paste support
  document.addEventListener('paste', (e) => {
    const it = [...e.clipboardData.items].find(i => i.type.startsWith('image/'));
    if (it) showFile(it.getAsFile());
  });

  $('#ocr-btn').addEventListener('click', async () => {
    if (!currentFile) return;
    flash($('#ocr-msg'), 'LLM 辨識中（可能需 10-30 秒）…', 'ok');
    const fd = new FormData();
    fd.append('image', currentFile);
    try {
      const r = await api('/api/step1/ocr', { method: 'POST', body: fd });
      ocrRows = r.rows;
      renderOcrTable(ocrRows);
      flash($('#ocr-msg'), `✓ 辨識到 ${ocrRows.length} 筆`, 'ok');
      $('#write1-btn').disabled = ocrRows.length === 0;
    } catch (err) {
      flash($('#ocr-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#write1-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#ocr-msg'), '請先填日期', 'err');
    // collect from editable table
    const rows = collectOcrTable();
    const fd = new FormData();
    fd.append('date', date);
    fd.append('rows', JSON.stringify(rows));
    try {
      const r = await api('/api/step1/write', { method: 'POST', body: fd });
      flash($('#ocr-msg'), `✓ 已寫入 ${r.range}`, 'ok');
    } catch (err) {
      flash($('#ocr-msg'), '✗ ' + err.message, 'err');
    }
  });
}

const OCR_COLS = [
  ['admit_date', '實際住院日'], ['op_date', '開刀日'],
  ['department', '科別'], ['doctor', '主治醫師'],
  ['icd_diagnosis', '主診斷ICD'], ['name', '姓名'],
  ['gender', '性別'], ['age', '年齡'],
  ['chart_no', '病歷號'], ['bed', '病床'],
  ['hint', '入院提示'], ['urgent', '住急'],
];

function renderOcrTable(rows) {
  const wrap = $('#ocr-table-wrap');
  if (!rows.length) { wrap.innerHTML = '<p class="hint">沒有資料</p>'; return; }
  const head = OCR_COLS.map(c => `<th>${c[1]}</th>`).join('');
  const body = rows.map((r, i) => '<tr>' + OCR_COLS.map(([k]) =>
    `<td><input data-row="${i}" data-col="${k}" value="${(r[k] || '').replace(/"/g, '&quot;')}"></td>`
  ).join('') + '</tr>').join('');
  wrap.innerHTML = `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function collectOcrTable() {
  const inputs = $$('#ocr-table-wrap input');
  const rows = [];
  inputs.forEach(inp => {
    const ri = +inp.dataset.row;
    rows[ri] = rows[ri] || {};
    rows[ri][inp.dataset.col] = inp.value;
  });
  return rows.filter(r => r && (r.name || '').trim());
}

// ---------- Step 2: Lottery ----------
let step2Patients = [];
let step2Ordered = [];

function setupStep2() {
  $('#load2-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    const weekday = $('#weekday').value;
    if (!date) return flash($('#s2-msg'), '請填日期', 'err');
    try {
      const r = await api(`/api/step2/context?date=${date}&weekday=${encodeURIComponent(weekday)}`);
      step2Patients = r.patients;
      renderTickets(r.tickets, step2Patients);
      flash($('#s2-msg'), `✓ ${r.patients.length} 位病人，抽籤表 ${Object.keys(r.tickets).length} 位醫師`, 'ok');
      $('#run2-btn').disabled = false;
    } catch (err) {
      flash($('#s2-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#run2-btn').addEventListener('click', async () => {
    const tickets = collectTickets();
    const date = $('#date-input').value.trim();
    const fd = new FormData();
    fd.append('date', date);
    fd.append('tickets_json', JSON.stringify(tickets));
    fd.append('seed', Math.floor(Math.random() * 1e6));
    try {
      const r = await api('/api/step2/run', { method: 'POST', body: fd });
      step2Ordered = r.ordered;
      renderOrdered(r.ordered);
      flash($('#s2-msg'), `✓ Round-robin ${r.ordered.length} 位`, 'ok');
      $('#write2-btn').disabled = false;
    } catch (err) {
      flash($('#s2-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#write2-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    const fd = new FormData();
    fd.append('date', date);
    fd.append('ordered_json', JSON.stringify(step2Ordered));
    try {
      const r = await api('/api/step2/write', { method: 'POST', body: fd });
      flash($('#s2-msg'), `✓ 已寫入 ${r.range}`, 'ok');
    } catch (err) {
      flash($('#s2-msg'), '✗ ' + err.message, 'err');
    }
  });
}

function renderTickets(tickets, patients) {
  const doctorsInData = [...new Set(patients.map(p => p.doctor).filter(Boolean))];
  // Merge: include doctors-from-sheet who aren't in tickets yet (they'll be "non-schedule")
  const all = { ...tickets };
  doctorsInData.forEach(d => { if (!(d in all)) all[d] = 0; });
  const html = Object.entries(all).map(([d, n]) =>
    `<div class="t"><label>${d}</label><input data-doc="${d}" type="number" min="0" value="${n}"></div>`
  ).join('');
  $('#tickets-wrap').innerHTML = `<h3>籤數（0 = 非時段）</h3><div class="tickets">${html}</div>`;
}

function collectTickets() {
  const out = {};
  $$('#tickets-wrap input[data-doc]').forEach(i => {
    const n = parseInt(i.value, 10) || 0;
    if (n > 0) out[i.dataset.doc] = n;
  });
  return out;
}

function renderOrdered(rows) {
  const body = rows.map((r, i) =>
    `<tr><td>${i + 1}</td><td>${r.doctor}</td><td>${r.name}</td><td>${r.chart_no || ''}</td></tr>`
  ).join('');
  $('#ordered-wrap').innerHTML = `
    <h3>抽籤結果 (round-robin)</h3>
    <table class="data"><thead><tr><th>序</th><th>主治</th><th>姓名</th><th>病歷號</th></tr></thead>
    <tbody>${body}</tbody></table>`;
}

// ---------- Step 3: EMR ----------
function setupStep3() {
  $('#run3-btn').addEventListener('click', async () => {
    const url = $('#session-url').value.trim();
    let patients;
    const raw = $('#emr-patients').value.trim();
    if (raw) {
      try { patients = JSON.parse(raw); }
      catch { return flash($('#s3-msg'), '病人 JSON 格式錯誤', 'err'); }
    } else {
      patients = step2Ordered;
    }
    if (!url || !patients || !patients.length)
      return flash($('#s3-msg'), '請填 session URL 並確定有病人清單', 'err');

    flash($('#s3-msg'), `擷取中… (${patients.length} 位)`, 'ok');
    const fd = new FormData();
    fd.append('session_url', url);
    fd.append('patients_json', JSON.stringify(patients));
    try {
      const r = await api('/api/step3/run', { method: 'POST', body: fd });
      renderEmrResults(r.results);
      flash($('#s3-msg'), `✓ 完成 ${r.results.length} 位`, 'ok');
    } catch (err) {
      flash($('#s3-msg'), '✗ ' + err.message, 'err');
    }
  });
}

function renderEmrResults(results) {
  const html = results.map(r => `
    <div class="emr-card">
      <h3>${r.doctor || ''} / ${r.name} (${r.chart_no}) ${r.error ? '⚠' : ''}</h3>
      ${r.error ? `<p class="msg err">${r.error}</p>` : ''}
      <pre>${(r.summary || '').replace(/</g, '&lt;')}</pre>
    </div>
  `).join('');
  $('#emr-results').innerHTML = html;
}

// ---------- Step 4: Ordering ----------
function setupStep4() {
  $('#load4-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s4-msg'), '請填日期', 'err');
    try {
      const r = await api(`/api/step4/subtables?date=${date}`);
      renderSubtables(r.tables);
      flash($('#s4-msg'), `✓ ${Object.keys(r.tables).length} 位醫師子表格`, 'ok');
      $('#integrate4-btn').disabled = false;
    } catch (err) {
      flash($('#s4-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#integrate4-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    const fd = new FormData();
    fd.append('date', date);
    try {
      const r = await api('/api/step4/integrate', { method: 'POST', body: fd });
      flash($('#s4-msg'), `✓ 已整合 ${r.rows} 筆到 ${r.range}`, 'ok');
    } catch (err) {
      flash($('#s4-msg'), '✗ ' + err.message, 'err');
    }
  });
}

function renderSubtables(tables) {
  const html = Object.entries(tables).map(([doc, pts]) => {
    const body = pts.map(p => `
      <tr>
        <td>${p.name}</td><td>${p.chart_no}</td>
        <td>${(p.diagnosis || '') || '<span class="msg err">—</span>'}</td>
        <td>${(p.cathlab || '') || '<span class="msg err">—</span>'}</td>
        <td>${p.note || ''}</td>
      </tr>`).join('');
    return `<div class="doctor-block"><h3>${doc}（${pts.length}人）</h3>
      <table class="data"><thead><tr><th>姓名</th><th>病歷號</th><th>術前診斷(F)</th><th>預計心導管(G)</th><th>註記</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }).join('');
  $('#subtables-wrap').innerHTML = html || '<p class="hint">沒找到子表格</p>';
}
