# Quality and scope of the curated 300 cases

The checked-out main baseline was 7210efd455407f2905f31dd44b1ed54270947802. No prior 300-record selection or manifest existed in the repository. The preceding task had explicitly stopped before dataset selection. Consequently no historical 300-row audit was fabricated. benchmark_300_audit.csv audits all 20,000 source rows and identifies the 300 selected rows. Their full original objects remain embedded in the curated JSONL.

The source was pinned to 37bd0f345efb166e3cebc6839e75481e57ce3c90. It contains three MIT-licensed JSON releases totaling 20,000 records. Checkout SHA-256 and canonical repository-blob SHA-256 are both recorded because Windows line endings change file bytes. LICENSE_INTENT_TX.txt preserves attribution.

| Source family | Rows | PASS | REJECT | Actual operation scope |
|---|---:|---:|---:|---|
| Compound V2 | 7,000 | 1,710 | 5,290 | deposit, withdraw, borrow, repay |
| CoW v2 | 7,000 | 1,710 | 5,290 | off-chain buy/sell order proposals |
| Uniswap V2 | 6,000 | 1,461 | 4,539 | single router swap calls |
| Total | 20,000 | 4,881 | 15,119 | zero genuine TRANSFER records |

The direct swap calls comprise 2,471 swapExactETHForTokens, 2,313 swapExactTokensForETH and 1,216 swapExactTokensForTokens. CoW orders were excluded from this single-call router benchmark. Lending was excluded. Recipient-related failures do not establish transfer-operation coverage.

**Compatibility has two different boundaries in this delivery.** All 300 cases are accepted by the existing Task Shield input and protocol-context schema for read-only alignment inference. The evaluator invokes the production TaskShield engine, user extraction, tool scoring and result validator with a real provider. All source transactions remain Ethereum Uniswap V2 transactions. All 300 have UNSUPPORTED_EXECUTION under PaceVant's current LOCAL/Fuji managed-vault policy. The number of source-native cases executable by the current LFJ/transfer pipeline is zero, a shortfall of 300 against any requirement for directly executable wallet cases. No Ethereum transaction was recast as LFJ and no call was broadcast. The reported alignment accuracy describes this component boundary.

**Context repair is substantive and explicit.** Source samples lack an executable historical pool quote. Each curated case therefore includes the same deterministic static-price-ratio reference formula, fixed source prices and source timestamp. The quote is computed before the label, using no gold label or prediction. The intent explicitly makes that fixture the benchmark's slippage reference. The quote is synthetic benchmark context and makes no assertion about historical AMM liquidity, fees or market impact. These 300 cases are labeled SOURCE_TRANSACTION_WITH_ADAPTED_SYNTHETIC_CONTEXT. They cannot substantiate an accuracy claim on untouched historical source data.

The exact original call parameters remain unchanged in all 300 cases. A redundant style descriptor is normalized to the actual function. Missing native ETH call value is normalized from the source's amountIn_human with its declared decimals. The source object is retained to make this reconstruction inspectable. USD sizing is evaluated with a declared one-cent display comparison against fixed prices. Unknown or synthetic tokens, ambiguous amounts, external private-routing/MEV conditions, incomplete intents and unresolved minimum/deadline constraints were excluded.

The conservative parser produced 1,435 eligible candidates before group deduplication. Source rows have unique IDs, but only 1,461 distinct Uniswap transaction hashes, 1,006 CoW hashes and 1,630 Compound hashes. A selected transaction hash appears only once. An additional semantic fingerprint removes near-duplicates across different hashes. The 300 final cases have 300 distinct source groups and semantic fingerprints.

| Target category | Requested | Final |
|---|---:|---:|
| ACCEPT | 100 | 68 |
| Token, amount, direction | 70 | 132 |
| Minimum output, slippage, deadline | 60 | 60 |
| Recipient/destination | 30 | 0 |
| Compatible technical violations | 40 | 40 |
| Total | 300 | 300 |

Quotas were applied in order to deterministic shuffled candidates, with unavailable slots filled from eligible unused source groups. No recipient edits or transfer cases were synthesized to meet a quota. Only 68 ACCEPT and no recipient-category rows were available under those grouped selection constraints. This statement concerns the eligible/deduplicated sampling procedure, not a proof that no other valid interpretation could produce another distribution.

Every selected row has MODIFY status because context was added. There are zero selected KEEP, REPLACE or EXCLUDE rows. At source-candidate level 18,565 rows were excluded and 1,135 eligible rows were left unselected. There was no pre-existing 300-row sample list to retain or replace. Selection uses seed 20261121. Split assignment is fixed by source-group hash, producing 56 development and 244 held-out cases. Cases were frozen before any model predictions. Selection was reproduced exactly from the source and the recorded eligible-candidate descriptors. The published JSONL uses LF line endings. The run manifest retains the original CRLF input-byte hash plus the canonical LF hash, and all 300 parsed objects were compared unchanged.

The original labels are preserved separately. The curated labels differ on 75 selected rows: 65 original PASS become REJECT and 10 original REJECT become ACCEPT. These differences include the effect of the declared reference context and the narrower alignment scope; they are not all claims that the original authors mislabeled historical transactions.

A separate scan flagged 191 original PASS rows with an explicit intent-token versus transaction-token discrepancy among fully parsed intents. The reported example uniswap_20251102_154231_99b35e79_aligned asks for DAI to WBTC while declaring USDC to ETH in the proposal. This discrepancy can be identified without inventing a quote. SOURCE_QUALITY.json records the flags and structural counts. No independent human reviewer participated.

Reference rules check token addresses, direction/path, fiat amount with explicit rounding, minimum received, static-reference slippage bound, deadline relative to source time, recipient syntax/nonzero, router/function compatibility and ABI integer width/required fields. The independent reference implementation has no import from the evaluated security modules. It establishes labels only for the declared model of the transaction. It does not establish liquidity, gas adequacy, sanctions, MEV outcome, code safety or execution success.

There are no generated transfer transactions, verified receipts, cross-workflow history or temporal-defense claims in this benchmark. Failure-node localization is limited by the actual Task Shield result schema, which exposes contribution explanations and a coarse TASK_MISALIGNED code. Exact field-localization accuracy is therefore unscored, rather than inferred from the expected answer.

Reproduce curation after checking out the pinned source commit.

```sh
uv run --locked python tools/evaluation/curate_single_transaction.py --dataset-dir /path/to/intent-tx-18k/dataset --output /tmp/curation-new
uv run --locked python -m pytest backend/tests/control/test_curated_benchmark.py -q
uv run --locked python tools/evaluation/evaluate_curated_single_transaction.py --output /tmp/benchmark-new --max-requests 650 --max-tokens 2000000 --concurrency 2
uv run --locked python tools/evaluation/report_curated_single_transaction.py --dataset fixtures/evaluation/curated-300/benchmark_300_curated.jsonl --run /tmp/benchmark-new --output /tmp/report-new
```

Inference uses the configured primary provider in .env, zero retries and no fallback providers. It checkpoints each completed prediction and every provider call. Resume requires the same dataset and public configuration. A canceled in-flight request can have consumed provider quota before a local checkpoint exists. Outputs with schema/provider failure remain in the denominator.
