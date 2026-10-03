const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const reviewBtn = document.getElementById('reviewBtn');
let selectedFile = null;

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

function setFile(file) {
  selectedFile = file;
  document.getElementById('dropText').textContent = `Selected: ${file.name}`;
  reviewBtn.disabled = false;
}

function esc(text) {
  return String(text).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

function statusBadge(status) {
  const map = {ok: 'ok', mismatch: 'bad', missing: 'warn', warning: 'warn', info: 'info'};
  return `<span class="badge ${map[status] || 'neutral'}">${status}</span>`;
}

reviewBtn.addEventListener('click', async () => {
  if (!selectedFile) return;
  reviewBtn.disabled = true;
  reviewBtn.textContent = 'Reviewing…';
  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('country', document.getElementById('reviewCountry').value);
  formData.append('exchange_rate', document.getElementById('reviewRate').value);

  let data;
  try {
    const resp = await fetch('/api/review', { method: 'POST', body: formData });
    data = await resp.json();
  } catch (e) {
    data = {ok: false, error: 'The server sent an unexpected reply. Please check the file is a real .xlsx and try again.'};
  }
  const box = document.getElementById('reviewResult');

  if (!data.ok) {
    box.innerHTML = `<div class="card"><span class="badge bad" style="white-space:normal;">${esc(data.error)}</span></div>`;
    reviewBtn.disabled = false; reviewBtn.textContent = 'Review Quotation';
    return;
  }

  let rows = data.checks.map(c => `
    <tr>
      <td>${esc(c.item)}</td>
      <td>${statusBadge(c.status)}</td>
      <td>${c.expected !== undefined ? '$' + c.expected : ''}</td>
      <td>${c.found !== undefined && c.found !== null ? '$' + c.found : esc(c.note || '—')}</td>
    </tr>
  `).join('');

  box.innerHTML = `
    <div class="card">
      <h2>Summary</h2>
      <div class="pill-row">
        <span class="badge neutral">File: ${esc(data.filename)}</span>
        <span class="badge neutral">Country used: ${esc(data.country_used || 'unknown')}</span>
        <span class="badge neutral">Rate used: ₹${data.rate_used} (from ${esc(data.rate_source)})</span>
      </div>
      <div class="summary-box" style="white-space:pre-wrap;">${esc(data.summary)}</div>
    </div>
    <div class="card">
      <h2>Line-by-line check</h2>
      <table>
        <tr><th>Item</th><th>Status</th><th>Expected</th><th>Found</th></tr>
        ${rows}
      </table>
    </div>
  `;
  reviewBtn.disabled = false;
  reviewBtn.textContent = 'Review Quotation';
});
