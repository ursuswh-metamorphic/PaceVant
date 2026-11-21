import {describe, expect, it} from 'vitest';
import {presetsFor} from '../components/attack-select';
import {beginAttempt, loadAttempt} from './recovery';

function storage(): Storage {
  const values = new Map<string, string>();
  return {length: 0, clear: () => values.clear(), key: () => null,
    getItem: key => values.get(key) ?? null, setItem: (key, value) => {values.set(key, value);},
    removeItem: key => {values.delete(key);}};
}

describe('adversarial demo requests', () => {
  it('exposes exactly two tests for each financial operation', () => {
    expect(presetsFor('payment').map(item => item.id)).toEqual(['payment-amount', 'payment-replay']);
    expect(presetsFor('swap').map(item => item.id)).toEqual(['swap-slippage', 'swap-route']);
  });
  it('retains the original attack and request key across interrupted responses', () => {
    const saved = storage();
    const first = beginAttempt('payment', saved, 'payment-replay');
    expect(loadAttempt(saved)?.body.attack).toBe('payment-replay');
    expect(beginAttempt('swap', saved, 'swap-route')).toEqual(first);
    expect(JSON.parse(saved.getItem('pacevant.judge.attempt.v1')!).body).toEqual({scenario: 'payment', attack: 'payment-replay'});
  });
});
