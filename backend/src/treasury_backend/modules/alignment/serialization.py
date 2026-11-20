"""Semantic view: preserve all text; commit complete opaque machine-byte literals."""

import hashlib
import re

from .provider import safe_value

HEX_BLOB = re.compile(r"0x(?:[0-9a-fA-F]{2}){66,}\Z")
HEX_VALUE = re.compile(r"0x[0-9a-fA-F]*\Z")
TRACE_FIELDS = {"type", "from", "to", "input", "output", "gas", "gasUsed", "value",
                "calls", "error", "revertReason", "failed", "returnValue", "structLogs",
                "depth", "op", "pc", "stack", "memory", "storage", "refund", "gasCost"}


def trace_view(trace):
    # VM bytes/numbers are data, never executable prompt instructions. Preserve EVERY
    # other string and unknown property name, including nested/trailing instructions.
    texts, contracts = set(), set()
    count = 0
    def visit(item):
        nonlocal count
        if isinstance(item, dict):
            count += 1
            for key, value in item.items():
                if key not in TRACE_FIELDS:
                    texts.add(str(key))
                visit(value)
        elif isinstance(item, list):
            for value in item:
                visit(value)
        elif isinstance(item, str):
            if HEX_VALUE.fullmatch(item):
                if len(item) == 42:
                    contracts.add(item)
            elif not item.isdecimal():
                texts.add(item)
    visit(trace)
    import json
    raw = json.dumps(trace, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"type": "VM_TRACE_TYPED_VIEW_FULL_TEXT", "sha256": hashlib.sha256(raw).hexdigest(),
            "byte_length": len(raw), "object_count": count, "contracts": sorted(contracts),
            "all_untrusted_text_literals_and_unknown_keys": sorted(texts),
            "instruction_authority": "NONE"}


def semantic_value(value):
    def compact(item):
        if isinstance(item, dict):
            return {k: trace_view(v) if k == "trace" and isinstance(v, (dict, list))
                    else compact(v) for k, v in item.items()}
        if isinstance(item, list):
            return [compact(v) for v in item]
        if isinstance(item, str) and HEX_BLOB.fullmatch(item):
            raw = bytes.fromhex(item[2:])
            return {"type": "OPAQUE_MACHINE_BYTES", "encoding": "hex",
                    "byte_length": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "instruction_authority": "NONE"}
        return item
    return compact(safe_value(value))
