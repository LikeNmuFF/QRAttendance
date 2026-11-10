// Run with: node python/tests/test_camera_preview.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const events = {}, timers = new Map();
let nextTimer = 0, responseOk = true, requests = 0;
const toggle = { addEventListener: (_, fn) => { events.click = fn; }, setAttribute() {} };
const image = { hidden: true, removeAttribute() {}, async decode() {} };
const label = {};
const placeholder = { hidden: false, querySelector: () => label };
const status = {};
const elements = { '[data-camera-toggle]': toggle, '.camera-image': image,
  '.camera-placeholder': placeholder, '.camera-status': status };
const panel = { dataset: { frameUrl: '/camera/frame' }, querySelector: key => elements[key] };
const document = {
  hidden: false,
  querySelector: key => key === '[data-camera-preview]' ? panel : null,
  querySelectorAll: () => [],
  addEventListener: (key, fn) => { events[key] = fn; },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../attendance/static/app.js'), 'utf8'), {
  document, window: { matchMedia: () => ({ matches: false }), addEventListener() {} },
  AbortController,
  URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
  setTimeout: (fn, delay) => { const id = ++nextTimer; timers.set(id, { fn, delay }); return id; },
  clearTimeout: id => timers.delete(id),
  fetch: async () => {
    requests++;
    return { ok: responseOk, status: responseOk ? 200 : 503,
      headers: { get: () => 'image/jpeg' }, blob: async () => ({}) };
  },
});
const settle = () => new Promise(resolve => setImmediate(resolve));
async function main() {
  events.click();
  await settle();
  assert.equal(image.hidden, false);
  assert.equal(status.textContent, 'Live preview');
  document.hidden = true;
  events.visibilitychange();
  assert.equal(image.hidden, true);
  assert.equal(timers.size, 0);
  document.hidden = false;
  events.visibilitychange();
  await settle();
  assert.equal(requests, 2);
  responseOk = false;
  const [id, timer] = [...timers].find(([, value]) => value.delay === 500);
  timers.delete(id);
  timer.fn();
  await settle();
  assert.equal(image.hidden, true);
  assert.equal(status.textContent, 'Check camera power and Wi-Fi');
  events.click();
  assert.equal(toggle.textContent, 'Start preview');
  assert.equal(timers.size, 0);
  console.log('Camera preview: live frame, hidden-tab pause, stale-frame removal and stop passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
