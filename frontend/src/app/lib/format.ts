import type {Evidence, Job, Workflow} from './types';

export function units(value: string | undefined, decimals = 6, precision = 6) {
  if (value === undefined || !/^-?\d+$/.test(value)) return 'Unavailable';
  let number = BigInt(value); const negative = number < 0n; if (negative) number = -number;
  const scale = 10n ** BigInt(decimals), tail = (number % scale).toString().padStart(decimals, '0').slice(0, precision).replace(/0+$/, '');
  return (negative ? '−' : '') + (number / scale).toLocaleString('en-US') + (tail ? '.' + tail : '');
}
export function short(value?: string, length = 6) {return value ? value.slice(0, length + 2) + '…' + value.slice(-length) : 'Unavailable';}
export function date(seconds?: number) {return seconds ? new Date(seconds * 1000).toLocaleString('en-GB', {timeZone:'Asia/Ho_Chi_Minh', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:false}) + ' UTC+7' : 'Unavailable';}
export function stage(workflow: Workflow | undefined, name: string): Evidence | undefined {return workflow?.timeline.slice().reverse().find(event => event.stage === name)?.evidence;}
export function intentAmount(workflow: Workflow | undefined) {
  if (!workflow) return 'Pending';
  const context = stage(workflow, 'OWNER_AUTHORITY');
  const token = workflow.intent.token_in.toLowerCase();
  if (token === String(context?.usdc).toLowerCase()) return units(workflow.intent.amount, 6, 8);
  if (token === String(context?.wavax).toLowerCase()) return units(workflow.intent.amount, 18, 8);
  return workflow.intent.amount + ' base units';
}
export function object(value: unknown): Evidence {return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Evidence : {};}
export function text(value: unknown, fallback = 'Unavailable') {return typeof value === 'string' || typeof value === 'number' ? String(value) : fallback;}
export function environment(value?: string) {return value === 'VERIFIED_REPLAY' ? 'Verified replay' : value === 'ANVIL_FORK' ? 'Fuji fork' : value === 'LOCAL_TEST' ? 'Local test' : value === 'REAL_FUJI_EXECUTION' ? 'Public Fuji' : 'Not verified';}
export function reason(code?: string) {
  const reasons: Record<string, string> = {
    LFJ_UNSUPPORTED_ROUTE:'The quoter selected a route outside the approved LFJ V1 pool.',
    ORACLE_PRICE_DEVIATION:'The quoted value falls outside the Owner’s allowed economic loss.',
    PAYEE_NOT_ALLOWED:'This recipient is not on the Owner-approved payment allowlist.',
    TASK_MISALIGNED:'The proposed action does not satisfy the authorized task or policy.',
    ORACLE_WINDOW_UNAVAILABLE:'A fresh verified Chainlink signing window is required.',
    FRESH_CHAINLINK_SIGNING_WINDOW_UNAVAILABLE:'The Chainlink round is too old for safe execution. Try a recorded demo or retry later.',
    STALE_OR_UNVERIFIED_CHAINLINK_PRICE:'The reference price is stale or could not be verified.',
    DEMO_BUSY:'Another isolated run is in progress. Your request is saved; retry shortly.',
    DEMO_RATE_LIMIT:'This visitor’s request allowance has been reached. Recorded evidence remains available.',
    DEMO_DAILY_LIMIT:'Today’s shared compute allowance has been reached.',
    DEMO_NOT_CONFIGURED:'The live fork worker is not configured. Verified recordings are available below.',
    DEMO_TIMEOUT:'The isolated run exceeded its bounded execution window and was stopped.',
    FORK_RUN_INTERRUPTED:'The service restarted during this isolated run. It was not automatically repeated.',
  };
  return code ? reasons[code] ?? code.replaceAll('_', ' ').toLowerCase() : 'The service could not verify an execution result.';
}
export function publicExplorer(job: Job): string | null {
  const outcome = job.workflow?.outcome;
  return job.environment !== 'VERIFIED_REPLAY' && outcome?.environment === 'REAL_FUJI_EXECUTION' && outcome.public_chain_receipt && /^0x[\da-f]{64}$/.test(outcome.tx_hash ?? '')
    ? 'https://testnet.snowtrace.io/tx/' + outcome.tx_hash : null;
}
