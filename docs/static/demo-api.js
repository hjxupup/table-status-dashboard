/* Offline API adapter for the original UI. Favorites belong to each visitor. */
(() => {
  'use strict';
  const storageKey = 'table-status-dashboard:favorites:v1';
  let favorites = {};
  try { favorites = JSON.parse(localStorage.getItem(storageKey) || '{}') || {}; }
  catch (_) { favorites = {}; }
  // Resolve relative to this script so /repo-name/ GitHub Pages works as well as /.
  const scriptUrl = document.currentScript.src;
  const dataset = (window.DASHBOARD_SNAPSHOT_DATA ? Promise.resolve(window.DASHBOARD_SNAPSHOT_DATA) : fetch(new URL('../data/snapshots.json', scriptUrl)).then(r => {
    if (!r.ok) throw new Error('Could not load archived metadata.');
    return r.json();
  })).then(payload => new Map(payload.snapshots.map(s => [s.table_name, s])));
  const response = (body, status = 200) => new Response(JSON.stringify(body), {
    status, headers: { 'Content-Type': 'application/json; charset=utf-8' }
  });
  const persist = () => {
    try { localStorage.setItem(storageKey, JSON.stringify(favorites)); } catch (_) { /* In-memory fallback. */ }
  };
  function metadata(source) {
    const data = JSON.parse(JSON.stringify(source));
    data.physical_size_gb = typeof data.physical_size_bytes === 'number'
      ? Math.round(data.physical_size_bytes / (1024 ** 3) * 10000) / 10000 : null;
    data.favorites = (Array.isArray(favorites[data.table_name]) ? favorites[data.table_name] : [])
      .filter(c => data.date_columns.includes(c)).slice(0, 5);
    data.default_favorite = null;
    data.source_mode = 'snapshot';
    return data;
  }
  window.dashboardDemoApi = async (url, options = {}) => {
    const tables = await dataset;
    const method = (options.method || 'GET').toUpperCase();
    const base = location.origin === 'null' ? 'https://dashboard.local' : location.origin;
    const path = new URL(url, base).pathname;
    if (path === '/api/ensure_data' && method === 'GET') {
      return response({ refreshing: false, has_data: tables.size > 0, validating: false,
                        initial_since: null, validation_since: null, source_mode: 'snapshot' });
    }
    if (path === '/api/refresh' && method === 'POST') {
      return response({ status: 'historical snapshot reloaded', source_mode: 'snapshot' }, 202);
    }
    const match = path.match(/^\/api\/table\/([^/]+)(?:\/(.*))?$/);
    if (!match) return response({ error: 'Unknown demo endpoint.' }, 404);
    const name = decodeURIComponent(match[1]);
    const source = tables.get(name);
    if (!source) return response({ error: 'Table not found.' }, 404);
    const action = match[2] || '';
    let body = {};
    try { body = options.body ? JSON.parse(options.body) : {}; }
    catch (_) { return response({ error: 'Invalid JSON.' }, 400); }
    const data = metadata(source);
    if ((!action && method === 'GET') || (action === 'refresh' && method === 'POST')) return response(data);
    if (action === 'time_spans' && method === 'GET') return response({
      table_name: name, columns: data.date_columns, spans: data.date_ranges,
      favorites: data.favorites, default_favorite: null
    });
    if (action === 'select_time_column' && method === 'POST') {
      if (!data.date_columns.includes(body.time_column)) return response({ error: 'Choose a valid time column.' }, 400);
      if (!(body.time_column in data.date_ranges)) return response({ error: 'No saved range for this column.' }, 422);
      return response(data);
    }
    if (action === 'favorite' && method === 'POST') {
      const col = body.column;
      if (!data.date_columns.includes(col)) return response({ error: 'Choose a valid time column.' }, 400);
      if (data.favorites.includes(col)) return response({ error: '已收藏此时间列' }, 400);
      if (data.favorites.length >= 5) return response({ error: '收藏不能超过五个' }, 400);
      favorites[name] = [col, ...data.favorites]; persist();
      return response({ ok: true, favorites: favorites[name], date_ranges: data.date_ranges });
    }
    if (action.startsWith('favorite/') && method === 'DELETE') {
      const col = decodeURIComponent(action.slice('favorite/'.length));
      if (!data.favorites.includes(col)) return response({ error: '不存在此收藏' }, 404);
      favorites[name] = data.favorites.filter(c => c !== col); persist();
      return response({ ok: true, favorites: favorites[name], date_ranges: data.date_ranges });
    }
    return response({ error: 'Unsupported demo action.' }, 405);
  };
})();
