function esc(text) {
  return String(text).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  try {
    return await resp.json();
  } catch (e) {
    return {ok: false, error: 'The server sent an unexpected reply (status ' + resp.status + '). Please try again.'};
  }
}

const container = document.getElementById('isItemsContainer');
const template = document.getElementById('isItemTemplate');

function addIsItem(data) {
  data = data || {};
  const clone = template.content.cloneNode(true);
  const card = clone.querySelector('.is-item-card');
  card.querySelector('.is-number').value = data.is_number || '';
  card.querySelector('.is-product').value = data.product_name || '';
  card.querySelector('.remove-is').addEventListener('click', () => card.remove());
  container.appendChild(clone);
}

document.getElementById('addIsBtn').addEventListener('click', () => addIsItem());

document.getElementById('parseBtn').addEventListener('click', async () => {
  const text = document.getElementById('commandInput').value.trim();
  if (!text) return;
  const btn = document.getElementById('parseBtn');
  btn.disabled = true; btn.textContent = 'Parsing…';
  try {
    const resp = await fetch('/api/parse-command', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text})
    });
    const data = await resp.json();
    if (data.client_name) document.getElementById('clientName').value = data.client_name;
    if (data.country) document.getElementById('country').value = data.country;
    if (data.is_numbers && data.is_numbers.length) {
      container.innerHTML = '';
      data.is_numbers.forEach(num => addIsItem({is_number: num}));
    }
  } catch (e) {
    alert('Could not parse command: ' + e);
  } finally {
    btn.disabled = false; btn.textContent = 'Parse';
  }
});

document.getElementById('refreshRate').addEventListener('click', async () => {
  const resp = await fetch('/api/exchange-rate');
  const data = await resp.json();
  document.getElementById('exchangeRate').value = data.rate;
  document.getElementById('rateSource').textContent = data.live ? 'Live rate' : 'Fallback rate — verify manually';
});

function collectIsItems() {
  return Array.from(document.querySelectorAll('.is-item-card')).map(card => ({
    is_number: card.querySelector('.is-number').value.trim(),
    product_name: card.querySelector('.is-product').value.trim(),
    sample_testing_usd: card.querySelector('.is-testing').value.trim(),
    min_marking_fee_usd: card.querySelector('.is-marking').value.trim(),
    consultancy_usd: card.querySelector('.is-consultancy').value.trim(),
    unit_price_inr: card.querySelector('.is-unit-price').value.trim(),
    unit_size: card.querySelector('.is-unit-size').value.trim(),
    annual_production: card.querySelector('.is-production').value.trim(),
  })).filter(i => i.is_number);
}

let lastQuotationPayload = null;

document.getElementById('calcBtn').addEventListener('click', async () => {
  const payload = {
    client_name: document.getElementById('clientName').value.trim(),
    country: document.getElementById('country').value.trim(),
    exchange_rate: document.getElementById('exchangeRate').value,
    is_items: collectIsItems(),
  };
  const box = document.getElementById('resultBox');
  box.style.display = 'block';
  lastQuotationPayload = null;
  const data = await postJson('/api/calculate', payload);
  if (!data.ok) {
    box.innerHTML = `<div class="badge bad" style="white-space:normal;">${esc(data.error)}</div>`;
    return;
  }
  lastQuotationPayload = payload;
  const r = data.result;
  let rows = '';
  rows += `<tr><td>Application Fee (x${r.n})</td><td>$${r.line_items.application_fee_usd_each} each</td></tr>`;
  rows += `<tr><td>Inspection Charge (${r.man_days} man-days)</td><td>$${r.line_items.inspection_usd}</td></tr>`;
  rows += `<tr><td>Travel expenses of BIS officer</td><td>$${r.line_items.travel_officer_usd}</td></tr>`;
  rows += `<tr><td>Per Diem (${r.per_diem_days} days @ $${r.per_diem_rate}/day)</td><td>$${r.line_items.per_diem_usd}</td></tr>`;
  rows += `<tr><td>Contingency funds</td><td>$${r.line_items.contingency_usd}</td></tr>`;
  rows += `<tr><td>Sample Testing Charges</td><td>$${r.line_items.sample_testing_per_is.join(', ')}</td></tr>`;
  rows += `<tr><td>Minimum Marking Fee / Year</td><td>$${r.line_items.min_marking_per_is.join(', ')}</td></tr>`;
  rows += `<tr><td>License Fee (x${r.n})</td><td>$${r.line_items.license_fee_usd_each} each</td></tr>`;
  rows += `<tr><td>PBG (not in total)</td><td>$${r.line_items.pbg_usd_each} each</td></tr>`;
  rows += `<tr><td>Consultancy Charges</td><td>$${r.line_items.consultancy_per_is.join(', ')}</td></tr>`;

  const warnings = (r.warnings || []).map(w =>
    `<div class="badge bad" style="display:block;margin-bottom:8px;white-space:normal;">&#9888; ${esc(w)}</div>`).join('');
  const confirmBox = r.country_recognized ? '' : `
    <label style="display:block;margin-top:12px;font-weight:600;">
      <input type="checkbox" id="countryConfirm"> I checked: "${esc(payload.country)}" really is outside USA/Europe/Turkey, so the standard rate is correct.
    </label>`;

  box.innerHTML = `
    ${warnings}
    <div class="pill-row">
      <span class="badge info">${esc(r.bracket_label)}</span>
      <span class="badge neutral">Rate used: ₹${r.exchange_rate}/USD</span>
    </div>
    <table>${rows}</table>
    <div class="total-line">Total (Excluding PBG): $${r.total_usd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
    ${confirmBox}
    <div style="margin-top:16px; display:flex; gap:10px;">
      <button class="btn" id="saveBtn">Save Quotation</button>
    </div>
  `;
  document.getElementById('saveBtn').addEventListener('click', saveQuotation);
});

async function saveQuotation() {
  const confirmBox = document.getElementById('countryConfirm');
  if (confirmBox && !confirmBox.checked) {
    alert('The country is not recognised. Correct it, or tick the confirmation box, before saving.');
    return;
  }
  const payload = Object.assign({}, lastQuotationPayload, {country_confirmed: !!(confirmBox && confirmBox.checked)});
  const data = await postJson('/api/save-quotation', payload);
  if (data.ok) {
    window.location.href = `/quotations/${data.quotation_id}`;
  } else {
    alert('Could not save: ' + data.error);
  }
}

// Load country suggestions
fetch('/api/countries').then(r => r.json()).then(countries => {
  const list = document.getElementById('countryList');
  countries.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c;
    list.appendChild(opt);
  });
});

addIsItem();
