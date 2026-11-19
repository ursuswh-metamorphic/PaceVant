# Business modules

Each folder owns a business capability and its README describes its entrypoints, inputs, outputs, extension rules and tests. Start with [backend/MODULES.md](../../../MODULES.md).

The normal workflow is planning -> alignment -> transaction build/simulation through the injected module adapter -> portfolio/risk/proof -> decision -> revalidation/signing -> execution -> monitoring. `workflows` composes the modules. `execution` cannot import signing or the operator layer. `core` contains shared types; it does not depend on feature modules.

Keep new feature tests beside the feature in `tests/`. Avoid a generic `utils` folder or unbounded cross-feature imports. A protocol/ABI change requires coordinated review of the SDK, both APIs and Solidity.
