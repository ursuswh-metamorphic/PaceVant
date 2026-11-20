export type ScenarioId = 'payment' | 'swap' | 'guard';
export type Json = null | boolean | number | string | Json[] | {[key: string]: Json};
export type Evidence = Record<string, Json>;
export interface StageEvent {stage: string; created_at: number; evidence: Evidence}
export interface Intent {operation: string; amount: string; token_in: string; token_out: string; recipient: string; treasury: string; objective: string; deadline: number; session_id: string; chain_id: number}
export interface Outcome {
  status: string; environment: string; public_chain_receipt: boolean;
  tx_hash?: string; gas_used?: string; actual_deltas?: string[]; payee_received?: string;
  block_number?: number; system_gas_expense?: {actual_cost_wei: string};
}
export interface Workflow {
  workflow_id: string; status: string; intent: Intent; created_at: number;
  reason_code?: string; environment?: string; timeline: StageEvent[]; outcome?: Outcome;
}
export type JobStatus = 'QUEUED' | 'RUNNING' | 'CONFIRMED' | 'REJECTED' | 'FAILED' | 'UNKNOWN' | 'INTERRUPTED' | 'UNAVAILABLE';
export interface Job {
  job_id: string; scenario: ScenarioId; status: JobStatus; created_at: number;
  environment: 'ANVIL_FORK' | 'LOCAL_TEST' | 'VERIFIED_REPLAY';
  active_stage?: string; phase?: string; reason_code?: string; workflow?: Workflow;
  semantic_scope?: string; source_block?: number; recorded_at?: number;
  public_chain_broadcast: false; terminal: boolean; scope?: string;
}
export interface Scenario {
  id: ScenarioId; title: string; description: string; operation: string; amount: string;
  input_decimals: number; token_in: string; token_out: string; recipient_label: string;
}
export interface JudgeConfig {
  enabled: boolean; mode: 'ANVIL_FORK'; configured: boolean; busy: boolean;
  reason_code?: string; scenarios: Scenario[];
  quota: {remaining_today: number; daily_limit: number; global_daily_limit: number};
  limits: {timeout_seconds: number; max_concurrent: number};
  replay_available: ScenarioId[]; semantic_scope: string;
  operator: {enabled: boolean; reason: string};
}
export interface SourceSnapshot {
  status: 'VERIFIED_READ' | 'RECORDED_SNAPSHOT' | 'UNAVAILABLE'; observed_at?: string;
  block_number?: number; chain_id?: number;
  balances?: {usdc: string; wavax: string};
  policy?: {paused: boolean; active: boolean; expires_at: number; max_relative_loss_bps: number; oracle_band_bps: number};
  oracle?: {status: string; updated_at?: number; age_seconds?: number; source?: string};
  addresses?: Record<string, string>; reason_code?: string;
}
