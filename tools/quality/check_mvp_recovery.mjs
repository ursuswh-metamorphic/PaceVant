import assert from 'node:assert/strict';
import {PendingRequest} from '../../frontend/src/features/mvp/requests.js';

class MemoryStorage {
  value = null;
  getItem() { return this.value; }
  setItem(_key, value) { this.value = value; }
  removeItem() { this.value = null; }
}
const missing = () => Object.assign(new Error('MVP_REQUEST_NOT_FOUND'), {code:'MVP_REQUEST_NOT_FOUND', status:404});
const body = {operation:'USDC_PAYMENT', amount:'10000', deadline:12345};

// Server completes payment but response is lost. Reload must recover it without a second POST.
{
  const storage = new MemoryStorage(), first = new PendingRequest(storage);
  const saved = first.begin('/mvp/workflows', body);
  let accepted = null, posts = 0;
  const api = async (path, options) => {
    if (!options) { if (!accepted) throw missing(); return accepted; }
    posts++; assert.equal(options.headers['Idempotency-Key'], saved.key);
    accepted = {workflow_id:'one-payment', status:'CONFIRMED'};
    throw new TypeError('Response lost after acceptance');
  };
  await assert.rejects(first.resume(api));
  const reload = new PendingRequest(storage);
  assert.equal(reload.current().key, saved.key);
  assert.equal((await reload.resume(api)).status, 'CONFIRMED');
  assert.equal(posts, 1); assert.equal(reload.current(), null);
}
// Request never reaches server. Retry must preserve the exact key, body and expiry.
{
  const storage = new MemoryStorage(), requests = new PendingRequest(storage);
  const input = {...body}, saved = requests.begin('/mvp/workflows', input);
  input.amount = '999999';
  let posts = 0;
  const api = async (_path, options) => {
    if (!options) throw missing();
    assert.equal(options.headers['Idempotency-Key'], saved.key);
    assert.deepEqual(JSON.parse(options.body), body);
    if (++posts === 1) throw new TypeError('Connection failed before acceptance');
    return {workflow_id:'same-request', status:'CONFIRMED'};
  };
  await assert.rejects(requests.resume(api));
  await new PendingRequest(storage).resume(api);
  assert.equal(posts, 2); assert.equal(storage.value, null);
}
// Pending requests survive polling and block another operation; overlapping resumes are single-flight.
{
  const storage = new MemoryStorage(), requests = new PendingRequest(storage);
  requests.begin('/mvp/workflows', body);
  assert.throws(() => requests.begin('/mvp/workflows', {...body, amount:'20000'}), /Resume/);
  let calls = 0;
  const api = async () => { calls++; await new Promise(resolve => setTimeout(resolve, 5)); return {workflow_id:'in-progress', status:'SIGNED'}; };
  await Promise.all([requests.resume(api), requests.resume(api)]);
  assert.equal(calls, 1); assert.equal(requests.current().workflow_id, 'in-progress');
  await requests.resume(async path => { assert.equal(path, '/mvp/workflows/in-progress'); return {status:'REVERTED'}; });
  assert.equal(requests.current(), null);
}
// Read-only polling never retransmits; auth/proxy failure retains the saved request.
{
  const requests = new PendingRequest(new MemoryStorage()); requests.begin('/mvp/workflows', body);
  await assert.rejects(requests.resume(async (_path, options) => { assert.equal(options, undefined); throw missing(); }, {readOnly:true}));
  await assert.rejects(requests.resume(async () => { throw Object.assign(new Error('AUTH_REQUIRED'), {code:'AUTH_REQUIRED', status:401}); }));
  assert.ok(requests.current());
}
// Browser storage failure blocks sending rather than losing the idempotency identity.
{
  const requests = new PendingRequest({getItem:() => null, setItem:() => { throw new Error('quota'); }});
  assert.throws(() => requests.begin('/mvp/workflows', body), /quota/);
}
console.log('PASS MVP recovery: lost responses, reload, exact retries, single-flight, read-only polling, auth and storage failure');
