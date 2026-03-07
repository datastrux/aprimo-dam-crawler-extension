// Audit report interactive filtering
// DATA is injected by the HTML template

function initializeReport(data, summary) {
  const DATA = data;
  const SUMMARY = summary;
  const rowsEl = document.getElementById('rows');
  const countEl = document.getElementById('count');
  const qEl = document.getElementById('q');
  const statusEl = document.getElementById('status');
  const urlTypeEl = document.getElementById('urlType');
  const needsEl = document.getElementById('needs');
  const clearBtn = document.getElementById('clearFilters');

  // Helper to get DAM preview URL or fallback to citizens image
  function getPreviewUrl(row) {
    // If matched to DAM and has item_id, construct DAM preview URL
    if (row.dam_item_id && row.match_status !== 'unmatched') {
      return `https://r1.aprimo.com/dam/asset/${row.dam_item_id}`;
    }
    // Otherwise use the citizens image URL
    return row.image_url;
  }

  // Helper to get DAM asset details URL
  function getDamDetailsUrl(itemId) {
    return `https://r1.aprimo.com/dam/asset/${itemId}`;
  }

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
      
      // Determine which image to show as thumbnail (prefer DAM preview if matched)
      const thumbnailSrc = r.url_contains_asset_id ? r.image_url : r.image_url;
      const thumbnailLink = r.dam_item_id ? getDamDetailsUrl(r.dam_item_id) : r.image_url;
      
      // Format page URLs with links
      const pageUrlsList = (r.page_urls || '').toString().split('|')
        .filter(url => url.trim())
        .map(url => `<a href="${url.trim()}" target="_blank" title="${url.trim()}">${url.trim()}</a>`)
        .join('<br/>');
      
      return `
      <tr>
        <td>
          <a href="${thumbnailLink}" target="_blank" class="thumbnail-link" title="Click to view ${r.dam_item_id ? 'in DAM' : 'full image'}">
            <img src="${thumbnailSrc}" class="thumbnail" alt="Preview" loading="lazy" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';" />
            <span style="display:none; font-size: 10px; color: #999;">No preview</span>
          </a>
        </td>
        <td><a href="${r.image_url}" target="_blank" style="font-size: 11px; word-break: break-all;">${r.image_url}</a></td>
        <td><span class="pill ${r.match_status}">${r.match_status}</span></td>
        <td>${urlBadge}</td>
        <td>${r.dam_item_id ? `<a href="${getDamDetailsUrl(r.dam_item_id)}" target="_blank">${r.dam_item_id}</a>` : ''}</td>
        <td style="font-size: 11px;">${r.dam_file_name || ''}</td>
        <td style="text-align: center;">${r.phash_distance ?? ''}</td>
        <td style="text-align: center;">${r.page_count ?? ''}</td>
        <td class="page-urls">${pageUrlsList}</td>
      </tr>
    `}).join('');

    countEl.textContent = `Rows: ${filtered.length} / ${DATA.length}`;
  }

  // Clear all filters
  clearBtn.addEventListener('click', () => {
    qEl.value = '';
    statusEl.value = '';
    urlTypeEl.value = '';
    needsEl.checked = false;
    render();
  });

  // Summary item clicks to filter table
  document.querySelectorAll('.summary-item').forEach(item => {
    item.addEventListener('click', () => {
      const filter = item.dataset.filter;
      
      // Reset filters first
      qEl.value = '';
      urlTypeEl.value = '';
      needsEl.checked = false;
      
      // Apply the filter based on summary item clicked
      if (filter === 'all') {
        statusEl.value = '';
      } else if (filter === 'needs_upload') {
        statusEl.value = '';
        needsEl.checked = true;
      } else if (filter === 'match_url_direct' || filter === 'match_exact' || filter === 'match_phash' || filter === 'unmatched') {
        statusEl.value = filter;
      }
      // Note: dam_exact_dupes, dam_phash_dupes, citizens_dupes would link to separate reports
      // For now, just scroll to details section
      
      document.querySelector('h2').scrollIntoView({ behavior: 'smooth', block: 'start' });
      render();
    });
  });

  qEl.addEventListener('input', render);
  statusEl.addEventListener('change', render);
  urlTypeEl.addEventListener('change', render);
  needsEl.addEventListener('change', render);
  render();
}
