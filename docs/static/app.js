function apiFetch(url, options) {
  return window.dashboardDemoApi ? window.dashboardDemoApi(url, options) : fetch(url, options);
}

function _setValue(card, key, value) {
  const el = card.querySelector(`[data-key="${key}"]`);
  if (!el) return;
  if (value === null || value === undefined) {
    el.textContent = '-';
    return;
  }

  // If element is marked as a numeric value, format with thousand separators
  if (el.classList && el.classList.contains('number')) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      el.textContent = value;
    } else {
      el.textContent = n.toLocaleString();
    }
    return;
  }

  el.textContent = value;
}

async function onTimeColumnChange(table, col) {
  const card = document.querySelector(`.table-card[data-table="${table}"]`);
  if (!card) return;
  if (!col) {
    _setValue(card, 'current_span', '-');
    return;
  }
  // Try to get spans first; if missing column, trigger backend selective compute
  try {
    const respSpans = await apiFetch(`/api/table/${encodeURIComponent(table)}/time_spans`);
    let spansData = respSpans.ok ? await respSpans.json() : null;
    if (!spansData || !spansData.spans || !(col in spansData.spans)) {
      // compute this column
      const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/select_time_column`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ time_column: col })
      });
      if (resp.ok) {
        const meta = await resp.json();
        spansData = { spans: meta.date_ranges, columns: meta.date_columns };
      }
    }
    if (spansData && spansData.spans && spansData.spans[col]) {
      const rng = spansData.spans[col];
      _setValue(card, 'current_span', `${rng.min_date} → ${rng.max_date}`);
    } else {
      _setValue(card, 'current_span', 'N/A');
    }
    updateFavoriteToggleStar(card, spansData, col);
  } catch (e) {
    console.error('onTimeColumnChange error', e);
    _setValue(card, 'current_span', 'Error');
  }
}

function applyDataToCard(card, data) {
  if (!card || !data) return;
  if ('analysis_time' in data) _setValue(card, 'analysis_time', formatWithWeekday(data.analysis_time));
  // 统一显示创建时间（作为“最后刷新”来源）
  if ('create_time' in data) _setValue(card, 'create_time', formatWithWeekday(data.create_time));
  if ('row_count' in data) _setValue(card, 'row_count', data.row_count ?? '-');
  if ('pk_distinct_count' in data) _setValue(card, 'pk_distinct_count', data.pk_distinct_count ?? '-');
  if ('column_count' in data) _setValue(card, 'column_count', data.column_count ?? '-');
  // show GB value (preferred)
  if ('physical_size_gb' in data) _setValue(card, 'physical_size_gb', data.physical_size_gb ?? '-');

  // populate select options
  const sel = card.querySelector('[data-key="time_select"]');
  if (sel && 'date_columns' in data) {
    const previous = sel.value;
    sel.innerHTML = '<option value="">-- 选择时间列 --</option>';
    if (data.date_columns && data.date_columns.length) {
      data.date_columns.forEach(c => {
        const o = document.createElement('option'); o.value = c; o.textContent = c; sel.appendChild(o);
      });
    }
    if (data.date_columns && data.date_columns.includes(previous)) {
      sel.value = previous;
      const range = (data.date_ranges || {})[previous];
      _setValue(card, 'current_span', range ? `${range.min_date} → ${range.max_date}` : 'N/A');
    } else {
      _setValue(card, 'current_span', '-');
    }
  }
  renderFavorites(card, data);
  updateFavoriteToggleStar(card, data, sel ? sel.value : null);
}

async function fetchTable(table) {
  const card = document.querySelector(`.table-card[data-table="${table}"]`);
  if (!card) return;
  _setValue(card, 'analysis_time', '');
  // show spinner
  const spinner = document.createElement('span'); spinner.className = 'spinner';
  const an = card.querySelector('[data-key="analysis_time"]');
  if (an) { an.textContent = ''; an.appendChild(spinner); }

  try {
    const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}`);
    if (!resp.ok) {
      throw new Error('未能获取表信息');
    }
    const data = await resp.json();
    applyDataToCard(card, data);
    return true;
  } catch (e) {
    console.error('fetchTable error', e);
    _setValue(card, 'analysis_time', 'N/A');
    const dr = card.querySelector('[data-key="date_ranges"]'); if (dr) dr.innerHTML = '<div class="placeholder">无法加载（后端或配置未启用）</div>';
    return false;
  }
}

function refreshCard(table) { fetchTable(table); }

async function refreshAnalyze(table) {
  const card = document.querySelector(`.table-card[data-table="${table}"]`);
  if (!card) return;
  const an = card.querySelector('[data-key="analysis_time"]');
  if (an) { an.textContent = ''; const sp = document.createElement('span'); sp.className='spinner'; an.appendChild(sp); }
  try {
    const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/refresh`, { method:'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || '失败');
    applyDataToCard(card, data);
    if (data.source_mode === 'snapshot') {
      const notice = document.getElementById('demo-action-notice');
      if (notice) notice.textContent = '· 已重新读取历史快照';
    }
    return true;
  } catch(e) {
    await fetchTable(table);
    alert('单表重新分析失败: '+ e.message);
    return false;
  }
}

async function loadTimeSpans(table) {
  const card = document.querySelector(`.table-card[data-table="${table}"]`);
  if (!card) return;
  try {
    const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/time_spans`);
    if (resp.ok) {
      const data = await resp.json();
      // adapt to applyDataToCard expected structure
      const merged = {
        date_columns: data.columns,
        date_ranges: data.spans,
        favorites: data.favorites,
        default_favorite: data.default_favorite,
        default_time_columns: [],
      };
      renderFavorites(card, merged);
      const select = card.querySelector('[data-key="time_select"]');
      updateFavoriteToggleStar(card, merged, select ? select.value : null);
    }
  } catch (e) { console.error('loadTimeSpans error', e); }
}

// 星标状态更新
function updateFavoriteToggleStar(card, data, currentCol) {
  const btn = card.querySelector('[data-key="fav_toggle"]');
  if (!btn) return;
  const star = btn.querySelector('.star');
  if (!currentCol) {
    btn.disabled = true;
    if (star) { star.classList.remove('filled'); star.textContent = '☆'; }
    return;
  }
  btn.disabled = false;
  const isFav = data && data.favorites && data.favorites.includes(currentCol);
  if (star) {
    if (isFav) { star.classList.add('filled'); star.textContent = '★'; }
    else { star.classList.remove('filled'); star.textContent = '☆'; }
  }
}

// 下拉旁星标点击收藏/取消
async function toggleFavoriteSelect(table) {
  const card = document.querySelector(`.table-card[data-table="${table}"]`);
  const sel = card.querySelector('[data-key="time_select"]');
  const col = sel && sel.value;
  if (!col) return;
  try {
    const dataResp = await apiFetch(`/api/table/${encodeURIComponent(table)}/time_spans`);
    const data = dataResp.ok ? await dataResp.json() : { favorites: [] };
    const isFav = data.favorites && data.favorites.includes(col);
    if (isFav) {
      const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/favorite/${encodeURIComponent(col)}`, { method: 'DELETE' });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.error || '失败');
    } else {
      const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/favorite`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ column: col }) });
      const json = await resp.json();
      if (!resp.ok) throw new Error(json.error || '失败');
      // 计算跨度，保证新收藏立即有范围
      await onTimeColumnChange(table, col);
    }
    await loadTimeSpans(table);
  } catch (e) { alert(e.message); }
}

async function removeFavorite(table, col) {
  try {
    const resp = await apiFetch(`/api/table/${encodeURIComponent(table)}/favorite/${encodeURIComponent(col)}`, { method: 'DELETE' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || '失败');
    const card = document.querySelector(`.table-card[data-table="${table}"]`);
    renderFavorites(card, { date_ranges: data.date_ranges, favorites: data.favorites });
    await loadTimeSpans(table);
  } catch (e) { alert(e.message); }
}

// 已移除默认收藏相关逻辑

// 更新所有缓存：仅重新获取各表当前缓存数据
async function updateAllCache() {
  const btn = document.getElementById('update-all-cache');
  if (!btn) return;
  btn.disabled = true; btn.textContent = '更新缓存中…';
  try {
    const cards = Array.from(document.querySelectorAll('.table-card'));
    const results = await Promise.all(cards.map(c => fetchTable(c.dataset.table)));
    if (results.some(ok => !ok)) throw new Error('部分表信息未能加载');
    const lr = document.getElementById('last-refresh');
    if (lr) lr.textContent = formatWithWeekday(new Date().toISOString());
  } catch(e) {
    alert('更新所有缓存失败: ' + (e.message || e));
  } finally {
    btn.disabled = false; btn.textContent = '更新所有缓存';
  }
}

// 重新分析所有：顺序执行，避免后端并发过高
async function reanalyzeAll() {
  const btn = document.getElementById('reanalyze-all');
  if (!btn) return;
  btn.disabled = true; btn.textContent = '重新分析中…';
  try {
    const cards = Array.from(document.querySelectorAll('.table-card'));
    for (const c of cards) {
      const ok = await refreshAnalyze(c.dataset.table);
      if (!ok) return;
    }
    const lr = document.getElementById('last-refresh');
    if (lr) lr.textContent = formatWithWeekday(new Date().toISOString());
  } catch(e) {
    alert('重新分析所有失败: ' + (e.message || e));
  } finally {
    btn.disabled = false; btn.textContent = '重新分析所有';
  }
}

document.addEventListener('DOMContentLoaded', function() {
  // initial fetch for all cards
  const cards = Array.from(document.querySelectorAll('.table-card'));
  cards.forEach(c => fetchTable(c.dataset.table));

  // 首屏自动检测：若短暂等待后所有卡片仍无有效分析时间，则自动触发一次批量缓存更新
  setTimeout(() => {
    const allEmpty = cards.length > 0 && cards.every(c => {
      const el = c.querySelector('[data-key="analysis_time"]');
      if (!el) return true;
      const t = (el.textContent || '').trim();
      return t === '' || t === '-' || t === 'N/A';
    });
    if (allEmpty) {
      updateAllCache();
    }
  }, 1200);

  // check if backend is doing initial refresh; show overlay and poll
  (async function checkEnsureData() {
    try {
      const resp = await apiFetch('/api/ensure_data');
      if (!resp.ok) return;
      const json = await resp.json();
      if (json.refreshing) {
        const overlay = document.getElementById('refresh-overlay');
        const secondsEl = document.getElementById('overlay-seconds');
        overlay.style.display = 'flex';
        const since = json.initial_since ? new Date(json.initial_since) : new Date();
        const interval = setInterval(async () => {
          const diff = Math.floor((Date.now() - since.getTime()) / 1000);
          secondsEl.textContent = diff;
          // poll to see if refresh finished
          const r2 = await apiFetch('/api/ensure_data');
          if (r2.ok) {
            const j2 = await r2.json();
            if (!j2.refreshing) {
              clearInterval(interval);
              overlay.style.display = 'none';
              // re-fetch cards once done
              const cards2 = Array.from(document.querySelectorAll('.table-card'));
              cards2.forEach(c => fetchTable(c.dataset.table));
            }
          }
        }, 1000);
      }
    } catch (e) {
      console.error('ensure_data check failed', e);
    }
  })();

  const btnUpdateAll = document.getElementById('update-all-cache');
  if (btnUpdateAll) btnUpdateAll.addEventListener('click', updateAllCache);
  const btnReAll = document.getElementById('reanalyze-all');
  if (btnReAll) btnReAll.addEventListener('click', reanalyzeAll);

  // 初次渲染头部 last-refresh 若是 UTC 字符串，转换本地
  const lr = document.getElementById('last-refresh');
  if (lr) lr.textContent = formatWithWeekday(lr.textContent);
});

function renderFavorites(card, data) {
  const favBox = card.querySelector('[data-key="favorites"]');
  if (!favBox) return;
  favBox.innerHTML = '';
  const spans = (data && data.spans) || data.date_ranges || {};
  if (data.favorites && data.favorites.length) {
    data.favorites.forEach(fc => {
      const row = document.createElement('div'); row.className = 'fav-row';
      const colSpan = spans[fc];
      const rngText = colSpan ? `${colSpan.min_date} → ${colSpan.max_date}` : '未计算';
      const colLabel = document.createElement('span'); colLabel.className = 'fav-col'; colLabel.textContent = fc;
      const rangeLabel = document.createElement('span'); rangeLabel.className = 'fav-span'; rangeLabel.textContent = rngText;
      row.append(colLabel, rangeLabel);
      const btn = document.createElement('button'); btn.className = 'icon-btn'; btn.title = '取消收藏';
      const star = document.createElement('span'); star.className = 'star filled'; star.textContent = '★';
      btn.appendChild(star);
      btn.onclick = () => removeFavorite(card.dataset.table, fc);
      row.appendChild(btn);
      favBox.appendChild(row);
    });
  }
}

function toLocalDisplay(src) {
  if (!src || src === '-' || typeof src !== 'string') return src || '-';
  const raw = src.trim();
  // 若是简单无时区的格式，直接保持原小时，不做时区换算，避免被当成 UTC 再 +8 小时
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)) {
    const [datePart, timePart] = raw.split(' ');
    const [Y,M,D] = datePart.split('-');
    return `${Y}/${M}/${D} ${timePart}`; // 不改变小时数字
  }
  // 其它包含 GMT/UTC/Z 的，交给 Date 解析再本地格式化
  if (/GMT|UTC|Z$/i.test(raw)) {
    const d = new Date(raw.replace(' ', 'T'));
    if (!isNaN(d.getTime())) {
      const pad = n => String(n).padStart(2,'0');
      return `${d.getFullYear()}/${pad(d.getMonth()+1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }
  }
  return raw; // 其它原样返回
}

// 格式: Mon YYYY/MM/DD HH:MM:SS 统一星期缩写 + 本地时间
function formatWithWeekday(src) {
  if (!src || src === '-' || src === 'N/A') return src || '-';
  const weekdays = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const raw = src.trim();
  // 无时区的标准格式直接拆分，不进行时区转换
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(raw)) {
    const [datePart, timePart] = raw.split(' ');
    const [Y,M,D] = datePart.split('-').map(n=>parseInt(n,10));
    const [h,mi,s] = timePart.split(':').map(n=>parseInt(n,10));
    const dObj = new Date(Y, M-1, D, h, mi, s);
    const pad = n => String(n).padStart(2,'0');
    return `${weekdays[dObj.getDay()]} ${Y}/${pad(M)}/${pad(D)} ${pad(h)}:${pad(mi)}:${pad(s)}`;
  }
  // 含 GMT/UTC/Z 的字符串用 Date 解析后本地显示
  if (/GMT|UTC|Z/i.test(raw)) {
    const d = new Date(raw.replace(' ', 'T'));
    if (!isNaN(d.getTime())) {
      const pad = n => String(n).padStart(2,'0');
      return `${weekdays[d.getDay()]} ${d.getFullYear()}/${pad(d.getMonth()+1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    }
  }
  // 尝试一般解析
  const d2 = new Date(raw);
  if (!isNaN(d2.getTime())) {
    const pad = n => String(n).padStart(2,'0');
    return `${weekdays[d2.getDay()]} ${d2.getFullYear()}/${pad(d2.getMonth()+1)}/${pad(d2.getDate())} ${pad(d2.getHours())}:${pad(d2.getMinutes())}:${pad(d2.getSeconds())}`;
  }
  return raw;
}
