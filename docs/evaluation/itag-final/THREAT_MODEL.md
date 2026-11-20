# Threat model

The protected assets are the vault balance, scoped user intent, replay-resistant approval and sponsor credit. A legitimate operator creates an IntentSpec for a bounded task. The proposed token, recipient, route, amount and purpose must be checked against its current revision and history. A proposal carrying a familiar token pair may still serve another purpose.

An external feed can supply misleading context, a planner can give an inaccurate rationale, a provider can produce invalid references, and an RPC view can be delayed or inconsistent. None is an authority to update intent. A model-extracted task is tagged MODEL_JUDGMENT, even when its parent message is authenticated. PRECEDES records ordering. A shared topic or similar rationale does not demonstrate causal influence.

A canonical matched receipt and reconciled outcome can count toward task consumption. An unresolved submission reserves capacity or triggers review. Missing, invalidated and conflicting evidence constrain continuation. Immutable decision/assessment bindings are checked again before signing. PolicyVault independently enforces the signed scope, nonce, limits and postconditions. A denied candidate may create an audit record. Signing and confirmed execution are recorded separately.

Experiments assume the operator and signer keys, local ledger, chain consensus and deployed bytecode are trustworthy within their respective profiles. Key compromise, malicious owner policy, model supply-chain compromise, economic manipulation of thin testnet pools, mainnet MEV, physical access, multi-tenant isolation and hosted failover are outside the measured security claim. We use declarative fixture histories and matched benign controls. No adversarial transaction was sent to a public chain.
