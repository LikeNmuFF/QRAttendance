// Run with: node python/tests/test_dashboard_live.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const events = {}, status = {}, button = {};
let tick, requests = 0, ok = true, redirected = false, cleared = false;
const parts = ['stats', 'attendance-rows', 'scan-feedback'].map(name => ({
  dataset: { livePart: name }, innerHTML: 'old',
  replaceChildren(child) { this.innerHTML = child.html; },
}));
const dashboard = {
  dataset: { dashboardLive: '/dashboard?date=2026-11-10' },
  querySelector: () => status, querySelectorAll: () => parts,
};
let searches = 0;
const search = { value: 'Maria', dispatchEvent: () => searches++ };
const schedule = { value: '09:00', readOnly: false,
  closest: () => ({ querySelector: () => button }) };
const document = {
  hidden: false,
  querySelector: selector => selector === '[data-dashboard-live]' ? dashboard : null,
  querySelectorAll: () => [],
  getElementById: id => id === 'attendance-search' ? search : schedule,
  addEventListener: (name, fn) => { events[name] = fn; },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../attendance/static/app.js'), 'utf8'), {
  document, window: { matchMedia: () => ({ matches: false }), addEventListener() {} },
  AbortController, Event,
  setTimeout: () => 1, clearTimeout() {},
  setInterval: fn => { tick = fn; return 1; }, clearInterval: () => { cleared = true; },
  DOMParser: class {
    parseFromString() {
      return { querySelector: selector => selector === '#start-time' ? { readOnly: true, value: '09:00' }
        : { innerHTML: 'new', childNodes: [{ html: 'new' }] } };
    }
  },
  fetch: async url => {
    assert.equal(url, '/dashboard?date=2026-11-10');
    requests++;
    return { ok, redirected, status: 200, text: async () => 'dashboard html' };
  },
});
const settle = () => new Promise(resolve => setImmediate(resolve));
async function main() {
  tick(); tick();
  await settle();
  assert.equal(requests, 1, 'refresh requests must not overlap');
  assert.ok(parts.every(part => part.innerHTML === 'new'));
  assert.equal(searches, 1);
  assert.equal(search.value, 'Maria', 'search text must survive refresh');
  assert.equal(schedule.value, '09:00', 'typed class time must survive refresh');
  assert.equal(schedule.readOnly, true);
  assert.notEqual(button.disabled, true, 'end time must remain editable');
  document.hidden = true;
  tick();
  await settle();
  assert.equal(requests, 1);
  document.hidden = false;
  ok = false;
  tick();
  await settle();
  assert.match(status.textContent, /Connection interrupted/);
  assert.ok(parts.every(part => part.innerHTML === 'new'), 'retain records on network errors');
  ok = true; redirected = true;
  tick();
  await settle();
  assert.equal(cleared, true);
  assert.match(status.textContent, /Session expired/);
  console.log('Dashboard refresh: records, search, form preservation, offline recovery and session expiry passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
