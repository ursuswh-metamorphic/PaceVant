# Business modules

> **DOC STATUS: MODULE_REFERENCE** - local interface/contribution reference, not a live readiness certification. The [current system design](../../../../docs/AI_Treasury_Security_System_Design_v2.1.md) owns the complete architecture/status; old reports linked below remain checkpoint-scoped.

Each folder owns a business capability and its README describes its entrypoints, inputs, outputs, extension rules and tests. Start with [backend/MODULES.md](../../../MODULES.md).

The normal workflow is planning -> alignment -> transaction build/simulation through the injected module adapter -> portfolio/risk/proof -> decision -> revalidation/signing -> execution -> monitoring. `workflows` composes the modules. `execution` cannot import signing or the operator layer. `core` contains shared types; it does not depend on feature modules.

Keep new feature tests beside the feature in `tests/`. Avoid a generic `utils` folder or unbounded cross-feature imports. A protocol/ABI change requires coordinated review of the SDK, both APIs and Solidity.
