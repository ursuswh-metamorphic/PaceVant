/*
 * Overview copy. Every factual claim here maps to something verifiable in the
 * product: the 12 workflowNodes, the recorded runs in fixtures/judge (Fuji fork,
 * public_chain_broadcast: false) or the contracts. No invented statistics.
 */

export type ShowcaseId = 'payment' | 'swap' | 'guard';

/** Facts taken from fixtures/judge/*.json (timeline length, created_at → last event). */
export const recordedRuns: Record<ShowcaseId, {stages: number; seconds: number; rejectAt?: number; reason?: string}> = {
  payment: {stages: 11, seconds: 18},
  swap: {stages: 11, seconds: 26},
  guard: {stages: 3, seconds: 7, rejectAt: 2, reason: 'LFJ_UNSUPPORTED_ROUTE'},
};

export const overviewCopy = {
  vi: {
    eyebrow: 'AI Agent Security trên Avalanche',
    headline: ['AI đề xuất giao dịch.', 'PaceVant xác minh trước khi Avalanche thực thi.'],
    description:
      'Lớp bảo mật giao dịch cho AI Agent: mô phỏng, đánh giá rủi ro, đối chiếu ý định và kiểm chứng on‑chain. Giao dịch chỉ được thực thi khi PolicyVault áp dụng đúng các điều kiện đã xác minh.',
    cta: 'Bắt đầu Demo',
    secondary: 'Xem cách hoạt động',
    showcase: {
      label: 'Xem lại các lần chạy đã ghi',
      window: 'Demo kiểm tra giao dịch',
      badge: 'Phát lại bản ghi',
      tabs: {
        payment: 'Thanh toán 0,01 USDC',
        swap: 'Hoán đổi USDC → WAVAX',
        guard: 'Tuyến swap không hỗ trợ',
      },
      scenario: {
        payment: ['Thanh toán USDC', '0,01 USDC → người nhận trong allowlist'],
        swap: ['Hoán đổi token', 'USDC → WAVAX qua pool LFJ được duyệt'],
        guard: ['Kiểm tra bảo mật', 'WAVAX → USDC qua tuyến LFJ không hỗ trợ'],
      },
      verdict: {
        running: ['Đang xác minh', 'Từng bước ghi bằng chứng trước khi bước sau bắt đầu.'],
        payment: ['Đã xác nhận', 'Đúng 0,01 USDC đến người nhận được duyệt; số dư đã đối soát.'],
        swap: ['Đã xác nhận', 'Hoán đổi trong giới hạn giá Chainlink, đầu ra tối thiểu được bảo vệ.'],
        guard: ['Bị chặn trước khi ký', 'Trusted Builder từ chối tuyến không được hỗ trợ. Không có gì được ký.'],
      },
      facts: ['Số bước kiểm tra', 'Thời gian xử lý', 'Mạng'],
      env: 'Fuji fork',
      modules: 'bước',
    },
    facts: [
      ['12', 'Bước bảo vệ giao dịch'],
      ['3', 'Giai đoạn xác minh'],
      ['43113', 'Chain ID Avalanche Fuji'],
      ['EIP‑712', 'Chữ ký ràng buộc giao dịch'],
      ['Z3', 'Kiểm chứng hình thức'],
    ],
    coreEyebrow: 'Công nghệ cốt lõi',
    coreTitle: '4 lớp bảo mật cho giao dịch của AI Agent',
    coreBody:
      'AI chỉ được đề xuất. Mỗi đề xuất đi qua mô phỏng, phân tích rủi ro, chứng minh hình thức rồi mới được ký và thực thi có kiểm soát trên Avalanche.',
    coreLink: 'Xem 12 bước',
    layers: [
      ['Xác minh ý định', 'Đối chiếu intent, policy và quyền giới hạn của AI Agent.'],
      ['Đánh giá rủi ro', 'Mô phỏng EVM, đo tác động tài sản và giới hạn tổn thất.'],
      ['Chứng minh hình thức', 'Z3 kiểm tra nghĩa vụ an toàn và biên dịch điều kiện Phi.'],
      ['Thực thi có ràng buộc', 'Ký EIP‑712, thực thi qua PolicyVault và đối soát Receipt.'],
    ],
    stack: [
      ['AI Agent', 'Chỉ đề xuất'],
      ['PaceVant Security', '12 bước xác minh'],
      ['PolicyVault', 'Thực thi atomic'],
      ['Avalanche', 'Fuji Testnet'],
    ],
    phasesEyebrow: 'Cách hoạt động',
    phasesTitle: 'Ba giai đoạn, mười hai bước',
    proofEyebrow: 'Kiểm chứng được',
    proofTitle: 'Bạn có thể kiểm chứng gì trên Fuji',
    proof: [
      ['Thanh toán USDC', 'Thanh toán đúng 0,01 USDC đến người nhận nằm trong allowlist, đối soát đến số tiền người nhận thực nhận.'],
      ['Hoán đổi USDC → WAVAX', 'Hoán đổi qua pool LFJ được duyệt, có giá Chainlink tham chiếu và đầu ra tối thiểu được bảo vệ.'],
      ['Bằng chứng từng bước', 'Mở từng bước để xem intent, mô phỏng, kết quả solver, attestation và receipt đã được ghi lại.'],
    ],
    proofCta: 'Mở trang Bằng chứng',
    ctaTitle: 'Chạy thử một giao dịch được bảo vệ',
    ctaBody: 'Chọn kịch bản, theo dõi từng lớp kiểm tra ra quyết định và xem bằng chứng thực thi trên Avalanche Fuji.',
    ctaSecondary: 'Xem bằng chứng',
    footerDescription: 'Bảo mật giao dịch AI Agent trên Avalanche.',
    footerProject: 'Built for UniHack · Avalanche Fuji Testnet',
    rights: 'PaceVant.',
  },
  en: {
    eyebrow: 'AI Agent Security on Avalanche',
    headline: ['AI proposes the transaction.', 'PaceVant verifies it before Avalanche executes.'],
    description:
      'A transaction-security layer for AI agents: simulation, risk bounds, intent checks and on‑chain enforcement. A transaction executes only when PolicyVault enforces the verified conditions.',
    cta: 'Start Demo',
    secondary: 'See how it works',
    showcase: {
      label: 'Replay recorded runs',
      window: 'Transaction verification demo',
      badge: 'Recorded replay',
      tabs: {
        payment: 'Pay 0.01 USDC',
        swap: 'Swap USDC → WAVAX',
        guard: 'Unsupported swap route',
      },
      scenario: {
        payment: ['USDC payment', '0.01 USDC → allowlisted recipient'],
        swap: ['Token swap', 'USDC → WAVAX through the approved LFJ pool'],
        guard: ['Security check', 'WAVAX → USDC through an unsupported LFJ route'],
      },
      verdict: {
        running: ['Verifying', 'Each step records evidence before the next one starts.'],
        payment: ['Confirmed', 'Exactly 0.01 USDC to the approved recipient; balances reconciled.'],
        swap: ['Confirmed', 'Swapped within Chainlink price bounds with protected minimum output.'],
        guard: ['Blocked before signing', 'Trusted Builder rejected the unsupported route. Nothing was signed.'],
      },
      facts: ['Checked stages', 'Processing time', 'Network'],
      env: 'Fuji fork',
      modules: 'steps',
    },
    facts: [
      ['12', 'Transaction security steps'],
      ['3', 'Verification phases'],
      ['43113', 'Avalanche Fuji chain ID'],
      ['EIP‑712', 'Transaction-bound signatures'],
      ['Z3', 'Formal verification'],
    ],
    coreEyebrow: 'Core technology',
    coreTitle: 'Four security layers for AI agent transactions',
    coreBody:
      'The AI may only propose. Every proposal is simulated, risk-checked and formally verified before it is signed and executed under guardrails on Avalanche.',
    coreLink: 'See the 12 steps',
    layers: [
      ['Intent verification', 'Check intent, policy and the agent’s limited authority.'],
      ['Risk assessment', 'Simulate in the EVM, measure asset effects and bound loss.'],
      ['Formal proof', 'Z3 checks safety obligations and compiles Phi conditions.'],
      ['Guarded execution', 'Sign EIP‑712, execute via PolicyVault and reconcile the receipt.'],
    ],
    stack: [
      ['AI Agent', 'Proposes only'],
      ['PaceVant Security', '12 verifying steps'],
      ['PolicyVault', 'Atomic enforcement'],
      ['Avalanche', 'Fuji Testnet'],
    ],
    phasesEyebrow: 'How it works',
    phasesTitle: 'Three phases, twelve steps',
    proofEyebrow: 'Verifiable',
    proofTitle: 'What you can verify on Fuji',
    proof: [
      ['USDC payment', 'Pay exactly 0.01 USDC to an allowlisted recipient, reconciled down to the amount actually received.'],
      ['USDC → WAVAX swap', 'Swap through the approved LFJ pool with a Chainlink reference price and protected minimum output.'],
      ['Evidence for every step', 'Open any step to inspect the recorded intent, simulation, solver results, attestation and receipt.'],
    ],
    proofCta: 'Open the Evidence page',
    ctaTitle: 'Run a protected transaction',
    ctaBody: 'Pick a scenario, watch each security layer decide, and review the execution evidence on Avalanche Fuji.',
    ctaSecondary: 'View evidence',
    footerDescription: 'Securing AI agent transactions on Avalanche.',
    footerProject: 'Built for UniHack · Avalanche Fuji Testnet',
    rights: 'PaceVant.',
  },
} as const;
