// Audit report interactive filtering
// DATA is injected by the HTML template

function initializeReport(data) {
  const DATA = data;
  const rowsEl = document.getElementById('rows');
  const countEl = document.getElementById('count');
  const qEl = document.getElementById('q');
  const statusEl = document.getElementById('status');
  const urlTypeEl = document.getElementById('urlType');
  const needsEl = document.getElementById('needs');

  function render() {
    const q = qEl.value.toLowerCase().trim();
    const status = statusEl.value;
    const urlType = urlTypeEl.value;
    const needsOnly = needsEl.checked;

    const filtered = DATA.filter(r => {
      if (status && r.match_status !== status) return false;
      if (urlType === 'direct_dam' && !r.url_contains_asset_id) return false;
      if (urlType === 'local_copy' && r.url_contains_asset_id) return false;
      if (needsOnly && !r.needs_dam_upload) return false;
      if (!q) return true;
      return [r.image_url, r.dam_item_id, r.dam_file_name, r.page_urls].join(' ').toLowerCase().includes(q);
    });

    rowsEl.innerHTML = filtered.map(r => {
      const urlBadge = r.url_contains_asset_id 
        ? '<span class="badge badge-dam">DAM URL</span>' 
        : '<span class="badge badge-local">Local</span>';
      
      return `
      <tr>
        <td><a href="${r.image_url}" target="_blank">${r.image_url}</a></td>
        <td><span class="pill ${r.match_status}">${r.match_status}</span></td>
        <td>${urlBadge}</td>
        <td>${r.dam_item_id || ''}</td>
        <td>${r.dam_file_name || ''}</td>
        <td>${r.phash_distance ?? ''}</td>
        <td>${r.page_count ?? ''}</td>
        <td>${(r.page_urls || '').toString().replace(/\|/g, '<br/>')}</td>
      </tr>
    `}).join('');

    countEl.textContent = `Rows: ${filtered.length} / ${DATA.length}`;
  }

  qEl.addEventListener('input', render);
  statusEl.addEventListener('change', render);
  urlTypeEl.addEventListener('change', render);
  needsEl.addEventListener('change', render);
  render();
}
