import assert from 'node:assert/strict';
import {approvalDeadline} from '../../frontend/src/features/mvp/terms.js';

// A still-valid round can expire before TTL; UI must use that earlier bound.
const context = {timestamp:1000, max_ttl:300, oracle_valid_until:1100,
  session_expires_at:2000, policy_expires_at:3000};
assert.equal(approvalDeadline(context, 1001), 1100);
assert.equal(approvalDeadline({...context, session_expires_at:1050}, 1001), 1050);
assert.throws(() => approvalDeadline(context, 1100), /expired/);
assert.throws(() => approvalDeadline({...context, oracle_valid_until:undefined}, 1001), /verified/);
console.log('PASS 4 MVP deadline cases: oracle, session, expiry, missing evidence');
