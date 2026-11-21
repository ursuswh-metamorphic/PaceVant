import {describe, expect, it} from 'vitest';
import {formatGasPaid} from './format';
import {bindingChain, compareBinding, evidenceScope, graphRecords, publicEvidence} from './security-evidence';
import type {Job} from './types';

describe('actual receipt gas precision', () => {
  it.each([['0', '0 AVAX'], ['41050', '0.00000000000004105 AVAX'], ['43783680', '0.00000000004378368 AVAX'], ['1000000000000000000', '1 AVAX']])('keeps exact wei %s', (input, expected) => expect(formatGasPaid(input)).toBe(expected));
  it.each([undefined, null, '', 'abc', '0.1', '-1', '1e9', {}, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])('never turns missing/malformed gas into zero', value => expect(formatGasPaid(value)).toBe('Unavailable'));
  it('localizes missing evidence', () => expect(formatGasPaid(undefined, 'vi')).toBe('Chưa có dữ liệu'));
});
describe('evidence trust boundaries', () => {
  it('missing hashes never match', () => {
    expect(compareBinding(undefined, undefined)).toBe('missing');
    expect(compareBinding('', '')).toBe('missing');
    expect(compareBinding('a', 'b')).toBe('mismatch');
    expect(compareBinding('a', 'a')).toBe('match');
    expect(bindingChain().every(link => link.state === 'missing')).toBe(true);
  });
  it('labels historical calls before public environment', () => expect(evidenceScope({environment: 'REAL_FUJI_EXECUTION', execution_kind: 'HISTORICAL_ETH_CALL'} as Job)).toBe('HISTORICAL FUJI ETH_CALL'));
  it('keeps recordings separate', () => expect(evidenceScope({environment: 'VERIFIED_REPLAY', workflow: {environment: 'ANVIL_FORK'}} as Job)).toBe('RECORDED · LOCAL ANVIL'));
  it('does not fabricate graph history or edges', () => {
    const graph = graphRecords({nodes: [{node_id: 'a'}, {node_id: 'b'}, {node_id: 'c'}], edges: [{source: 'a', target: 'b'}]});
    expect(graph.nodes).toHaveLength(3); expect(graph.edges).toHaveLength(1);
    expect(graphRecords({}).nodes).toEqual([]);
    expect(graphRecords({nodes: [{node_id: 'a'}], edges: [{source: 'a', target: 'unknown'}]}).edges).toEqual([]);
  });
  it('keeps public commitments and drops signing capability recursively', () => {
    expect(publicEvidence({proof_hash: 'public', signature: 'never-render', nested: {private_key: 'secret', raw_transaction: 'signed-bytes'}, same_original_signature: true})).toEqual({proof_hash: 'public', nested: {}, same_original_signature: true});
  });
});
