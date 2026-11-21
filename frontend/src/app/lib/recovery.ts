import type {ScenarioId} from './types';

export interface SavedAttempt {key: string; body: {scenario: ScenarioId; attack?: string}; job_id?: string; created_at: number}
const KEY = 'pacevant.judge.attempt.v1';
const VIEW_KEY = 'pacevant.judge.view.v1';
export interface ViewedRun {job_id:string;scenario:ScenarioId}
export function loadViewedRun(storage:Storage=sessionStorage):ViewedRun|null {
  const raw=storage.getItem(VIEW_KEY);if(!raw)return null;
  try {
    const value=JSON.parse(raw) as ViewedRun;
    return /^judge_[a-f0-9]{32}$/.test(value.job_id)&&['payment','swap','guard'].includes(value.scenario)?value:null;
  } catch {return null;}
}
export function saveViewedRun(value:ViewedRun,storage:Storage=sessionStorage){storage.setItem(VIEW_KEY,JSON.stringify(value));}
export function clearViewedRun(storage:Storage=sessionStorage){storage.removeItem(VIEW_KEY);}
export function loadAttempt(storage: Storage = sessionStorage): SavedAttempt | null {
  const raw = storage.getItem(KEY); if (!raw) return null;
  const value = JSON.parse(raw) as SavedAttempt;
  if (typeof value.key !== 'string' || !['payment', 'swap', 'guard'].includes(value.body?.scenario)) throw new Error('Saved request is unreadable. Inspect History before clearing tab data.');
  return value;
}
export function saveAttempt(value: SavedAttempt, storage: Storage = sessionStorage) {storage.setItem(KEY, JSON.stringify(value));}
export function beginAttempt(scenario: ScenarioId, storage: Storage = sessionStorage, attack?: string): SavedAttempt {
  const previous = loadAttempt(storage);
  if (previous) return previous;
  if (!globalThis.crypto?.randomUUID) throw new Error('A secure HTTPS connection is required to start a demo.');
  const value = {key:crypto.randomUUID(), body:{scenario, ...(attack ? {attack} : {})}, created_at:Date.now()};
  saveAttempt(value, storage); return value;
}
export function clearAttempt(storage: Storage = sessionStorage) {storage.removeItem(KEY);}
