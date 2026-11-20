# Fixed-operation execution infrastructure

The canonical live extension is `execution/mvp.py` (`MvpExecution`), restricted to swaps and exact USDC payments. These files share deterministic builds, disposable Anvil simulation, EIP-712 execution, the existing raw-transaction journal and canonical effect reconciliation.

`V3Execution`, ERC-4626/native-payment paths and `operations/v3_local.py` are isolated research/test code from the earlier expansion request. Canonical application startup rejects their activation. They must not be registered as an MVP agent tool or enabled by the old V3 environment setting.

Inputs: authenticated typed intent, owner-signed registry, pinned policy/session/token/oracle facts. Outputs: immutable build/effect artifacts, exact signed preflight, journaled transaction and measured outcome. Amounts are integer base-unit strings. Shared SDK proof/signing lives outside execution; execution never imports the attestor module or obtains Owner authority.

See root `MVP_FINAL_ARCHITECTURE.md`, `MVP_ECONOMIC_RISK_AUDIT.md` and `MVP_DEMO_RUNBOOK.md` for scope, assumptions, budgets, migration and verification limits.
