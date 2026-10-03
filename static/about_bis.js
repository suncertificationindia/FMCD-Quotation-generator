function esc(text) {
  return String(text).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

const cards = Array.from(document.querySelectorAll('.std-card'));
const badge = (cls, text) => `<div class="badge ${cls}" style="display:block;margin-bottom:6px;white-space:normal;">${esc(text)}</div>`;

cards.forEach(card => {
  const upload = card.querySelector('.std-upload');
  const scopeDetails = card.querySelector('.scope-details');
  const fileInput = card.querySelector('.std-file');
  card.querySelectorAll('.std-have').forEach(radio => radio.addEventListener('change', async () => {
    const msg = card.querySelector('.std-msg');
    const preview = card.querySelector('.std-preview');
    preview.innerHTML = '';
    if (radio.value === 'yes') {
      upload.style.display = 'block'; scopeDetails.style.display = 'block';
      msg.innerHTML = fileInput.files.length ? msg.innerHTML : '';
      return;
    }
    upload.style.display = 'none'; scopeDetails.style.display = 'none';
    fileInput.value = ''; card.querySelector('.std-scope-img').value = '';
    msg.innerHTML = '<span class="muted">Looking up the year and name on the BIS website...</span>';
    let data;
    try {
      const resp = await fetch('/api/standard-meta?is=' + encodeURIComponent(card.dataset.number));
      data = await resp.json();
    } catch (e) {
      data = {ok: false, error: 'The BIS website could not be reached. Please type the year and name.'};
    }
    let html = badge('info', 'Standard not available: it will not appear on the Scope slide or in the standards zip.');
    if (data.ok) {
      if (data.year) card.querySelector('.std-year').value = data.year;
      if (data.description) card.querySelector('.std-desc').value = data.description;
    } else {
      html += badge('bad', data.error);
    }
    msg.innerHTML = html;
  }));

  fileInput.addEventListener('change', async () => {
    const msg = card.querySelector('.std-msg');
    const preview = card.querySelector('.std-preview');
    preview.innerHTML = '';
    if (!fileInput.files.length) { msg.innerHTML = ''; return; }
    msg.innerHTML = '<span class="muted">Reading the standard...</span>';
    const fd = new FormData();
    fd.append('file', fileInput.files[0]);
    fd.append('expected', card.dataset.number);
    let data;
    try {
      const resp = await fetch('/api/standard-info', {method: 'POST', body: fd});
      data = await resp.json();
    } catch (e) {
      data = {ok: false, error: 'The server sent an unexpected reply. Please try again.'};
    }
    if (!data.ok) { msg.innerHTML = badge('bad', data.error); return; }
    if (data.year) card.querySelector('.std-year').value = data.year;
    if (data.description) card.querySelector('.std-desc').value = data.description;
    let html = data.warnings.map(w => badge('bad', w)).join('');
    if (!data.mismatch) {
      html += badge('ok', `Read: IS ${data.is_number} : ${data.year || '?'} - ${data.description || 'name not found'}`);
    }
    msg.innerHTML = html;
    if (data.previews.length) {
      preview.innerHTML = '<div class="muted">Scope found - this picture goes into the presentation:</div>' +
        data.previews.map(src => `<img src="${src}" style="max-width:100%;border:1px solid var(--border);border-radius:6px;margin-top:6px;">`).join('');
    }
  });
});

document.getElementById('fetchBtn').addEventListener('click', async () => {
  const btn = document.getElementById('fetchBtn');
  const msg = document.getElementById('fetchMsg');
  btn.disabled = true; btn.textContent = 'Fetching...';
  msg.innerHTML = '';
  let data;
  try {
    const resp = await fetch('/api/bis-data', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({is_numbers: cards.map(c => c.dataset.number)})
    });
    data = await resp.json();
  } catch (e) {
    data = {ok: false, error: 'The server sent an unexpected reply. Please try again.'};
  }
  btn.disabled = false; btn.textContent = 'Fetch from BIS';
  if (!data.ok) { msg.innerHTML = badge('bad', data.error); return; }
  cards.forEach(card => {
    const n = data.fmcs[card.dataset.number];
    if (n !== undefined) card.querySelector('.std-fmcs').value = n;
    const title = (data.manuals || {})[card.dataset.number];
    const status = card.querySelector('.manual-status');
    if (title) {
      status.innerHTML = badge('ok', 'Product manual found on the BIS website: ' + title);
    } else {
      status.innerHTML = badge('bad', 'No product manual for this standard was found on the BIS website. Add the file below.');
      card.querySelector('.manual-details').open = true;
    }
  });
  if (data.labs.length) document.getElementById('labs').value = data.labs.join('\n');
  document.getElementById('labsEtc').checked = !!data.more;
  msg.innerHTML = data.errors.map(e => badge('bad', e)).join('') +
    badge('ok', `Foreign licensee counts filled in. ${data.labs.length} labs listed${data.more ? ' (more exist, so ", etc" is ticked)' : ''}.`);
});

async function build(mode) {
  const msg = document.getElementById('buildMsg');
  const fd = new FormData();
  fd.append('mode', mode);
  fd.append('count', cards.length);
  cards.forEach((card, i) => {
    const answer = card.querySelector('.std-have:checked');
    fd.append('have_' + i, answer ? answer.value : '');
    const file = card.querySelector('.std-file').files[0];
    if (answer && answer.value === 'yes') {
      if (file) fd.append('std_' + i, file);
      const img = card.querySelector('.std-scope-img').files[0];
      if (img) fd.append('scope_img_' + i, img);
    }
    const manual = card.querySelector('.std-manual').files[0];
    if (manual) fd.append('manual_' + i, manual);
    fd.append('year_' + i, card.querySelector('.std-year').value.trim());
    fd.append('desc_' + i, card.querySelector('.std-desc').value.trim());
    fd.append('date_' + i, card.querySelector('.std-date').value);
    fd.append('india_' + i, card.querySelector('.std-india').value);
    fd.append('fmcs_' + i, card.querySelector('.std-fmcs').value);
  });
  fd.append('labs', document.getElementById('labs').value);
  fd.append('labs_etc', document.getElementById('labsEtc').checked ? '1' : '0');
  const buttons = [document.getElementById('packBtn'), document.getElementById('pdfBtn')];
  buttons.forEach(b => b.disabled = true);
  msg.innerHTML = '<span class="muted">Preparing the files... this can take up to a minute.</span>';
  try {
    const resp = await fetch(`/quotations/${window.QID}/about-bis/build`, {method: 'POST', body: fd});
    const type = resp.headers.get('Content-Type') || '';
    if (!resp.ok || type.includes('application/json')) {
      let error = 'Something went wrong. Please try again.';
      try { error = (await resp.json()).error || error; } catch (e) {}
      msg.innerHTML = badge('bad', error);
    } else {
      const blob = await resp.blob();
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = match ? decodeURIComponent(match[1]) : (mode === 'pack' ? 'Document pack.zip' : 'About BIS.pdf');
      document.body.appendChild(link); link.click(); link.remove();
      msg.innerHTML = badge('ok', 'Done - the file has been downloaded.');
    }
  } catch (e) {
    msg.innerHTML = badge('bad', 'The connection failed. Please try again.');
  }
  buttons.forEach(b => b.disabled = false);
}

document.getElementById('packBtn').addEventListener('click', () => build('pack'));
document.getElementById('pdfBtn').addEventListener('click', () => build('pdf'));
