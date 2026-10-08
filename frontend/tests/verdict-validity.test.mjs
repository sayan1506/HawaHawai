import {test} from 'node:test';
import assert from 'node:assert/strict';
import {verdictExpired} from '../src/verdictValidity.ts';

const deadline = '2026-10-08T09:00:00Z';
const now = Date.parse(deadline);
test('recommendation is usable only before its explicit deadline', () => assert.equal(verdictExpired(deadline, now - 1), false));
test('exact expiry and later times require recheck', () => {
  assert.equal(verdictExpired(deadline, now), true);
  assert.equal(verdictExpired(deadline, now + 1), true);
});
test('malformed deadlines or evaluation clocks fail closed', () => {
  assert.equal(verdictExpired('invalid', now), true);
  assert.equal(verdictExpired(deadline, NaN), true);
});
test('timezone-equivalent deadlines have identical expiry', () => assert.equal(verdictExpired('2026-10-08T14:30:00+05:30', now), true));
