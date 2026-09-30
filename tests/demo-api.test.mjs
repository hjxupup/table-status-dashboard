import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const payload = JSON.parse(readFileSync(new URL('../data/snapshots.json', import.meta.url), 'utf8'));
const code = readFileSync(new URL('../tools/demo-api.js', import.meta.url), 'utf8');

function demo(origin, embedded = false, storage = new Map()) {
  const window = embedded ? { DASHBOARD_SNAPSHOT_DATA: payload } : {};
  let networkRequests = 0;
  const context = {
    window, location: { origin }, URL, Response, console,
    document: { currentScript: { src: embedded ? '' : `${origin}/portfolio/static/demo-api.js` } },
    localStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v) },
    fetch: async url => {
      networkRequests++;
      assert.equal(String(url), `${origin}/portfolio/data/snapshots.json`);
      return new Response(JSON.stringify(payload));
    },
  };
  vm.runInNewContext(code, context);
  return { request: window.dashboardDemoApi, storage, networkRequests: () => networkRequests };
}

for (const [origin, embedded] of [['https://demo.example', false], ['null', true]]) {
  test(`all archived cards and refresh work with origin ${origin}`, async () => {
    const api = demo(origin, embedded);
    for (const expected of payload.snapshots) {
      const path = `/api/table/${encodeURIComponent(expected.table_name)}`;
      const response = await api.request(path);
      assert.equal(response.status, 200);
      const before = await response.json();
      const after = await (await api.request(`${path}/refresh`, { method: 'POST' })).json();
      assert.equal(before.row_count, expected.row_count);
      assert.equal(after.analysis_time, expected.analysis_time);
      assert.deepEqual(after.date_ranges, expected.date_ranges);
    }
    assert.equal(api.networkRequests(), embedded ? 0 : 1);
    assert.equal((await api.request('/api/table/unknown')).status, 404);
  });
}

test('favorites are limited, persistent and isolated between visitors', async () => {
  const api = demo('https://demo.example');
  const sample = payload.snapshots.find(s => s.date_columns.length >= 6);
  const path = `/api/table/${encodeURIComponent(sample.table_name)}`;
  const favorite = col => api.request(`${path}/favorite`, { method: 'POST', body: JSON.stringify({ column: col }) });
  for (const col of sample.date_columns.slice(0, 5)) assert.equal((await favorite(col)).status, 200);
  assert.equal((await favorite(sample.date_columns[5])).status, 400);
  assert.equal((await favorite('not_a_time_column')).status, 400);
  const saved = demo('https://demo.example', false, api.storage);
  assert.equal((await (await saved.request(`${path}/time_spans`)).json()).favorites.length, 5);
  const visitor = demo('https://demo.example');
  assert.equal((await (await visitor.request(`${path}/time_spans`)).json()).favorites.length, 0);
  const col = encodeURIComponent(sample.date_columns[0]);
  assert.equal((await api.request(`${path}/favorite/${col}`, { method: 'DELETE' })).status, 200);
  assert.equal((await (await api.request(path)).json()).favorites.length, 4);
});
