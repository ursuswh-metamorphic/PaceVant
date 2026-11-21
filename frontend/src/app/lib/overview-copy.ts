export const overviewCopy = {
  vi: {
    tagline: 'AI Agent Security · Avalanche',
    headline: ['AI đề xuất giao dịch.', 'PaceVant', 'kiểm tra bảo mật và ràng buộc on‑chain.', 'Avalanche', 'thực thi trong giới hạn đó.'],
    description:
      'Lớp bảo mật giao dịch cho AI Agent: mỗi giao dịch được đối chiếu ý định, mô phỏng, đánh giá rủi ro và chỉ được thực thi khi PolicyVault áp dụng đúng các điều kiện đã xác minh.',
    cta: 'Bắt đầu Demo',
    secondary: 'Xem cách hoạt động',
    helper: 'Không cần ví, tài khoản hay token. Chọn kịch bản và chạy thử.',
    preview: {
      window: 'Luồng kiểm tra giao dịch',
      badge: 'Minh hoạ',
      agent: ['AI Agent', 'Đề xuất giao dịch'],
      core: ['PaceVant', 'Kiểm tra & xác minh'],
      chain: ['Avalanche', 'Thực thi có ràng buộc'],
      facts: [
        ['Giao dịch mẫu', 'Thanh toán 0,01 USDC'],
        ['Lớp kiểm tra', '12 module'],
        ['Ràng buộc', 'PolicyVault'],
        ['Mạng', 'Fuji Testnet'],
      ],
      caption: 'Sơ đồ minh hoạ. Kết quả thật chỉ xuất hiện khi chạy Live Demo.',
    },
    aboutTitle: 'PaceVant là gì?',
    aboutBody:
      'Lớp kiểm soát nằm giữa AI Agent và blockchain. AI chỉ được đề xuất; PaceVant xác minh đề xuất đó, ký điều kiện bảo vệ và để hợp đồng trên Avalanche thực thi chúng.',
    features: [
      ['Xác minh ý định', 'Đúng yêu cầu, đúng người nhận'],
      ['Đánh giá rủi ro', 'Mô phỏng và giới hạn tổn thất'],
      ['Ràng buộc on‑chain', 'Điều kiện Phi ký bằng EIP‑712'],
      ['Thực thi có kiểm soát', 'PolicyVault kiểm tra atomic'],
    ],
    story: [
      {
        title: 'Vì sao giao dịch của AI Agent cần guardrails?',
        body: 'AI có thể đề xuất sai ý định, dựa trên giá không còn hiệu lực hoặc vượt quyền được cấp. Khi nắm tài sản thật, một đề xuất sai là một khoản mất thật.',
      },
      {
        title: 'PaceVant xác minh như thế nào?',
        body: 'Mô phỏng EVM đo tác động thực tế, Risk Engine giới hạn tổn thất, Shield + ITAG đối chiếu ý định và Z3 chứng minh điều kiện an toàn trước khi ký.',
      },
      {
        title: 'Ràng buộc được thực thi trên Avalanche',
        body: 'Chữ ký EIP-712 gắn với giao dịch, nonce, thời hạn và Phi. PolicyVault từ chối mọi tác động nằm ngoài điều kiện đã xác minh.',
      },
    ],
    phasesTitle: 'Ba giai đoạn, mười hai module',
    phasesBody:
      'Đây cũng là bố cục của sơ đồ trong Live Demo. Mỗi module chỉ đổi trạng thái khi backend ghi nhận bằng chứng của nó.',
    proofTitle: 'Bạn có thể kiểm chứng gì trên Fuji',
    proof: [
      ['Thanh toán USDC', 'Thanh toán đúng 0,01 USDC đến người nhận nằm trong allowlist, đối soát đến số tiền người nhận thực nhận.'],
      ['Hoán đổi USDC → WAVAX', 'Hoán đổi qua pool LFJ được duyệt, có giá Chainlink tham chiếu và đầu ra tối thiểu được bảo vệ.'],
      ['Bằng chứng cho từng bước', 'Mở từng module để xem intent, mô phỏng, kết quả solver, attestation và receipt đã được ghi lại.'],
    ],
    ctaTitle: 'Chạy thử một giao dịch được bảo vệ',
    ctaBody: 'Chọn kịch bản, theo dõi từng lớp kiểm tra và xem bằng chứng thực thi trên Avalanche Fuji.',
    ctaSecondary: 'Xem bằng chứng',
    footerDescription: 'Bảo mật giao dịch AI Agent trên Avalanche.',
    footerProject: 'Built for UniHack · Avalanche Fuji Testnet',
    rights: 'PaceVant.',
  },
  en: {
    tagline: 'AI Agent Security · Avalanche',
    headline: ['AI proposes transactions.', 'PaceVant', 'verifies them and enforces on‑chain guardrails.', 'Avalanche', 'executes within those limits.'],
    description:
      'A transaction-security layer for AI agents: every transaction is checked against intent, simulated and risk-bounded, and executes only when PolicyVault enforces the verified conditions.',
    cta: 'Start Demo',
    secondary: 'See how it works',
    helper: 'No wallet, account or tokens needed. Pick a scenario and run it.',
    preview: {
      window: 'Transaction verification flow',
      badge: 'Illustration',
      agent: ['AI Agent', 'Proposes a transaction'],
      core: ['PaceVant', 'Checks & verifies'],
      chain: ['Avalanche', 'Executes under guardrails'],
      facts: [
        ['Sample transaction', 'Pay 0.01 USDC'],
        ['Security layers', '12 modules'],
        ['Enforcement', 'PolicyVault'],
        ['Network', 'Fuji Testnet'],
      ],
      caption: 'Illustrative diagram. Real results appear only when you run the Live Demo.',
    },
    aboutTitle: 'What is PaceVant?',
    aboutBody:
      'A control layer between AI agents and the blockchain. The AI may only propose; PaceVant verifies the proposal, signs protective conditions and lets a contract on Avalanche enforce them.',
    features: [
      ['Intent verification', 'Right request, right recipient'],
      ['Risk assessment', 'Simulation and loss bounds'],
      ['On-chain guardrails', 'Phi conditions signed via EIP-712'],
      ['Guarded execution', 'Atomic PolicyVault checks'],
    ],
    story: [
      {
        title: 'Why do AI agent transactions need guardrails?',
        body: 'An agent can misread intent, act on stale prices or exceed the authority it was given. With real assets, a wrong proposal is a real loss.',
      },
      {
        title: 'How does PaceVant verify?',
        body: 'EVM simulation measures actual effects, the Risk Engine bounds loss, Shield + ITAG check intent, and Z3 proves safety conditions before anything is signed.',
      },
      {
        title: 'Guardrails enforced on Avalanche',
        body: 'The EIP-712 signature binds the transaction, nonce, deadline and Phi. PolicyVault rejects any effect outside the verified conditions.',
      },
    ],
    phasesTitle: 'Three phases, twelve modules',
    phasesBody:
      'This is also the layout of the Live Demo graph. A module changes state only when the backend records evidence for it.',
    proofTitle: 'What you can verify on Fuji',
    proof: [
      ['USDC payment', 'Pay exactly 0.01 USDC to an allowlisted recipient, reconciled down to the amount the recipient actually received.'],
      ['USDC → WAVAX swap', 'Swap through the approved LFJ pool with a Chainlink reference price and a protected minimum output.'],
      ['Evidence for every step', 'Open any module to inspect the recorded intent, simulation, solver results, attestation and receipt.'],
    ],
    ctaTitle: 'Run a protected transaction',
    ctaBody: 'Pick a scenario, watch each security layer decide, and review the execution evidence on Avalanche Fuji.',
    ctaSecondary: 'View evidence',
    footerDescription: 'Securing AI agent transactions on Avalanche.',
    footerProject: 'Built for UniHack · Avalanche Fuji Testnet',
    rights: 'PaceVant.',
  },
} as const;
