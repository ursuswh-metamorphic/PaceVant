import type {ScenarioId} from './types';

export interface SavedAttempt {key: string; body: {scenario: ScenarioId}; job_id?: string; created_at: number}
const KEY = 'pacevant.judge.attempt.v1';
export function loadAttempt(storage: Storage = sessionStorage): SavedAttempt | null {
  const raw = storage.getItem(KEY); if (!raw) return null;
  const value = JSON.parse(raw) as SavedAttempt;
  if (typeof value.key !== 'string' || !['payment', 'swap', 'guard'].includes(value.body?.scenario)) throw new Error('Saved request is unreadable. Inspect History before clearing tab data.');
  return value;
}
export function saveAttempt(value: SavedAttempt, storage: Storage = sessionStorage) {storage.setItem(KEY, JSON.stringify(value));}
export function beginAttempt(scenario: ScenarioId, storage: Storage = sessionStorage): SavedAttempt {
  const previous = loadAttempt(storage);
  if (previous) return previous;
  if (!globalThis.crypto?.randomUUID) throw new Error('A secure HTTPS connection is required to start a demo.');
  const value = {key:crypto.randomUUID(), body:{scenario}, created_at:Date.now()};
  saveAttempt(value, storage); return value;
}
export function clearAttempt(storage: Storage = sessionStorage) {storage.removeItem(KEY);}
