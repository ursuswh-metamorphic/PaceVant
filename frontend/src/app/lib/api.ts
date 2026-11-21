import type {JudgeConfig, Job, SourceSnapshot} from './types';

export class ApiError extends Error {
  constructor(public code: string, public status: number) {super(code);}
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {...options, credentials:'same-origin', redirect:'error', signal:AbortSignal.timeout(30000),
    headers:{Accept:'application/json', ...options.headers}});
  let value;
  try { value = await response.json(); } catch { throw new ApiError('RESPONSE_UNAVAILABLE', response.status); }
  if (!response.ok) throw new ApiError(value.error?.code ?? 'REQUEST_FAILED', response.status);
  return value as T;
}
export const api = {
  config: () => request<JudgeConfig>('/judge/config'),
  snapshot: () => request<SourceSnapshot>('/judge/source'),
  history: () => request<{jobs: Job[]}>('/judge/history'),
  job: (id: string) => request<Job>('/judge/jobs/' + encodeURIComponent(id)),
  byKey: (key: string) => request<Job>('/judge/requests/' + encodeURIComponent(key)),
  start: (scenario: string, key: string, attack?: string) => request<Job>('/judge/jobs', {method:'POST', headers:{'Content-Type':'application/json', 'Idempotency-Key':key}, body:JSON.stringify({scenario, ...(attack ? {attack} : {})})}),
  replay: (scenario: string) => request<Job>('/judge/replays/' + encodeURIComponent(scenario)),
};
