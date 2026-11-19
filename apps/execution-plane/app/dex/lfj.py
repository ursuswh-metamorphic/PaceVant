"""Fuji LFJ registry, pinned discovery/quotes and immutable direct V1 execution route.

ABI definitions: official traderjoe-xyz/joe-v2 ILBRouter.sol and LBQuoter.sol (MIT).
Only read RPC methods are used here. A DEX quote is never a USD oracle.
"""

from eth_abi import decode, encode
from web3 import Web3

from ..crypto import keccak
from ..errors import PlaneError

CHAIN_ID = 43113
ROUTER = Web3.to_checksum_address("0x18556DA13313f3532c54711497A8FedAC273220E")
QUOTER = Web3.to_checksum_address("0x9A550a522BBaDFB69019b0432800Ed17855A51C3")
USDC = Web3.to_checksum_address("0xB6076C93701D6a07266c31066B298AeC6dd65c2d")
WAVAX = Web3.to_checksum_address("0xd00ae08403B9bbb9124bB305C09058E32C39A48c")
ADAPTER_VERSION = "lfj-v1-fuji-v1"
REGISTRY = "https://developers.lfj.gg/deployment-addresses/fuji"
QUOTE_TYPE = "(address[],address[],uint256[],uint8[],uint128[],uint128[],uint128[])"
VERSIONS = {0: "V1", 1: "V2", 2: "V2_1", 3: "V2_2"}


def call(w3, address, signature, types=(), values=(), returns=("uint256",), block="latest"):
    data = Web3.keccak(text=signature)[:4] + encode(types, values)
    try:
        raw = w3.eth.call(
            {"to": Web3.to_checksum_address(address), "data": data}, block_identifier=block
        )
        result = decode(returns, raw)
        if encode(returns, result) != raw:
            raise ValueError("noncanonical ABI")
        return result
    except Exception:
        raise PlaneError("LFJ_CALL_FAILED", f"LFJ read failed: {signature}", 503) from None


class LFJClient:
    def __init__(self, w3):
        self.w3 = w3
        if w3.eth.chain_id != CHAIN_ID:
            raise PlaneError("CHAIN_MISMATCH", "LFJ execution requires Avalanche Fuji 43113")

    def code_hash(self, address, block):
        code = self.w3.eth.get_code(Web3.to_checksum_address(address), block)
        if not code:
            raise PlaneError("LFJ_CONTRACT_MISSING", "LFJ/token contract has no bytecode", 503)
        return keccak(code)

    def token(self, address, expected_decimals, block):
        (decimals,) = call(self.w3, address, "decimals()", returns=("uint8",), block=block)
        if decimals != expected_decimals:
            raise PlaneError("TOKEN_DECIMALS_MISMATCH", "Unsupported token denomination")
        (symbol,) = call(self.w3, address, "symbol()", returns=("string",), block=block)
        return {
            "address": address,
            "decimals": decimals,
            "symbol": symbol,
            "bytecode_hash": self.code_hash(address, block),
        }

    def quote(self, amount, block):
        if type(amount) is not int or not 0 < amount < 2**128:
            raise PlaneError("INVALID_QUOTE_AMOUNT", "LFJ quote requires a positive uint128")
        (values,) = call(
            self.w3,
            QUOTER,
            "findBestPathFromAmountIn(address[],uint128)",
            ("address[]", "uint128"),
            ([USDC, WAVAX], amount),
            (QUOTE_TYPE,),
            block,
        )
        route, pairs, steps, versions, amounts, virtual, fees = values
        if (
            len(amounts) != 2
            or amounts[0] != amount
            or len(pairs) != 1
            or not amounts[-1]
            or int(pairs[0], 16) == 0
        ):
            raise PlaneError(
                "NO_LIQUIDITY", "LFJ quoter found no executable direct USDC/WAVAX route", 409
            )
        if (
            [a.lower() for a in route] != [USDC.lower(), WAVAX.lower()]
            or len(steps) != 1
            or len(versions) != 1
            or len(virtual) != 2
            or len(fees) != 1
        ):
            raise PlaneError("LFJ_INVALID_ROUTE", "Malformed LFJ quote")
        return {
            "source": "LFJ_LBQUOTER_V2_2",
            "router": ROUTER,
            "quoter": QUOTER,
            "token_path": route,
            "pairs": pairs,
            "bin_steps": list(steps),
            "versions": list(versions),
            "version_names": [VERSIONS[v] for v in versions],
            "amounts": [str(x) for x in amounts],
            "virtual_amounts_without_slippage": [str(x) for x in virtual],
            "fees_e18": [str(x) for x in fees],
            "amount_in_base_units": str(amount),
            "amount_out_base_units": str(amounts[-1]),
            "block_number": block,
            "block_hash": Web3.to_hex(self.w3.eth.get_block(block).hash),
        }

    def v1_route(self, block):
        (factory,) = call(self.w3, ROUTER, "getV1Factory()", returns=("address",), block=block)
        (native,) = call(self.w3, ROUTER, "getWNATIVE()", returns=("address",), block=block)
        (q_router,) = call(self.w3, QUOTER, "getRouterV2_2()", returns=("address",), block=block)
        (q_factory,) = call(self.w3, QUOTER, "getFactoryV1()", returns=("address",), block=block)
        (pair,) = call(
            self.w3,
            factory,
            "getPair(address,address)",
            ("address", "address"),
            (USDC, WAVAX),
            ("address",),
            block,
        )
        if int(pair, 16) == 0:
            raise PlaneError("NO_LIQUIDITY", "LFJ V1 pair does not exist", 409)
        (t0,) = call(self.w3, pair, "token0()", returns=("address",), block=block)
        (t1,) = call(self.w3, pair, "token1()", returns=("address",), block=block)
        (pf,) = call(self.w3, pair, "factory()", returns=("address",), block=block)
        if (
            {t0.lower(), t1.lower()} != {USDC.lower(), WAVAX.lower()}
            or pf != factory
            or q_factory != factory
            or q_router.lower() != ROUTER.lower()
            or native.lower() != WAVAX.lower()
        ):
            raise PlaneError("LFJ_INVALID_ROUTE", "Pair/quoter/router identity mismatch")
        r0, r1, _ = call(
            self.w3, pair, "getReserves()", returns=("uint112", "uint112", "uint32"), block=block
        )
        if min(r0, r1) == 0:
            raise PlaneError("NO_LIQUIDITY", "LFJ V1 reserves are empty", 409)
        return {
            "lfj_router": ROUTER,
            "lfj_quoter": QUOTER,
            "pair": Web3.to_checksum_address(pair),
            "factory": Web3.to_checksum_address(factory),
            "version": 0,
            "version_name": "V1",
            "bin_step": 0,
            "token_path": [USDC, WAVAX],
            "token0": t0,
            "token1": t1,
            "reserves": [str(r0), str(r1)],
            "bytecode_hashes": {
                "LFJRouter": self.code_hash(ROUTER, block),
                "LFJQuoter": self.code_hash(QUOTER, block),
                "LFJPair": self.code_hash(pair, block),
                "LFJFactory": self.code_hash(factory, block),
            },
        }

    def verified_quote(self, amount, block, route=None):
        route = route or self.v1_route(block)
        quote = self.quote(amount, block)
        if (
            quote["pairs"][0].lower() != route["pair"].lower()
            or quote["versions"] != [0]
            or quote["bin_steps"] != [0]
        ):
            raise PlaneError(
                "LFJ_UNSUPPORTED_ROUTE",
                "Best route changed; adapter only supports the verified direct V1 pool",
                409,
            )
        # Independently recompute the *same DEX* quote from V1 reserves. Not an oracle.
        r0, r1 = map(int, route["reserves"])
        ri, ro = (r0, r1) if route["token0"].lower() == USDC.lower() else (r1, r0)
        expected = amount * 997 * ro // (ri * 1000 + amount * 997)
        if int(quote["amount_out_base_units"]) != expected:
            raise PlaneError(
                "LFJ_QUOTE_MISMATCH", "Quoter and selected pool reserves disagree", 409
            )
        return {**quote, "route": route, "independent_usd_oracle": False}

    def discover(self, block):
        result = []
        for version, getter in [
            (1, "getLegacyFactory()"),
            (2, "getFactoryV2_1()"),
            (3, "getFactory()"),
        ]:
            (factory,) = call(self.w3, ROUTER, getter, returns=("address",), block=block)
            (pairs,) = call(
                self.w3,
                factory,
                "getAllLBPairs(address,address)",
                ("address", "address"),
                (USDC, WAVAX),
                ("(uint16,address,bool,bool)[]",),
                block,
            )
            for step, pair, created, ignored in pairs:
                entry = {
                    "version": version,
                    "version_name": VERSIONS[version],
                    "factory": factory,
                    "pair": pair,
                    "bin_step": step,
                    "ignored_for_routing": ignored,
                    "bytecode_hash": self.code_hash(pair, block),
                }
                # V2 legacy has a different reserve ABI; balances are valid observations for all.
                entry["token_balances"] = {
                    symbol: str(
                        call(
                            self.w3, token, "balanceOf(address)", ("address",), (pair,), block=block
                        )[0]
                    )
                    for symbol, token in [("USDC", USDC), ("WAVAX", WAVAX)]
                }
                result.append(entry)
        return result

    def preflight(self, amounts=(100_000, 1_000_000, 10_000_000)):
        block = self.w3.eth.get_block("latest")
        n = block.number
        result = {
            "schema_version": "lfj-preflight-v1",
            "chain_id": CHAIN_ID,
            "broadcast": False,
            "registry_url": REGISTRY,
            "block_number": n,
            "block_hash": Web3.to_hex(block.hash),
            "block_timestamp": block.timestamp,
            "status": "INCONCLUSIVE",
            "tokens": [self.token(USDC, 6, n), self.token(WAVAX, 18, n)],
            "discovered_lb_pairs": self.discover(n),
            "quotes": [],
            "risk_blockers": ["ORACLE_TOKEN_IDENTITY_MISMATCH"],
            "oracle_note": "LFJ faucet USDC is not Circle USDC and has no verified independently priced redemption/peg. Never assume $1.",
        }
        try:
            route = self.v1_route(n)
            result["selected_route"] = route
            for amount in amounts:
                result["quotes"].append(self.verified_quote(amount, n, route))
            result["status"] = "QUOTE_VERIFIED_EXECUTION_NOT_YET_SIMULATED"
        except PlaneError as e:
            result["status"] = e.code
        if Web3.to_hex(self.w3.eth.get_block(n).hash) != result["block_hash"]:
            raise PlaneError("HASH_MISMATCH", "Fuji block changed during preflight", 409)
        return result
