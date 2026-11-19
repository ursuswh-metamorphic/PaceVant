"""Public read-only portfolio acquisition; never loads signing settings or wallet keys."""

import argparse
from pathlib import Path

from pydantic import TypeAdapter, ValidationError  # noqa: E402

from treasury_backend.core.domain import Address  # noqa: E402
from treasury_backend.core.errors import ControlError  # noqa: E402
from treasury_backend.core.models import Mandate  # noqa: E402
from treasury_backend.modules.persistence import Store  # noqa: E402
from treasury_backend.modules.portfolio.observations import PortfolioReader  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help="Public Vault/account address, not a private key")
    parser.add_argument("--mode", choices=["FUJI", "LOCAL"], default="FUJI")
    parser.add_argument("--rpc-url", default="https://api.avax-test.network/ext/bc/C/rpc")
    parser.add_argument("--mandate", type=Path)
    parser.add_argument("--db", type=Path, help="Optionally persist an immutable observation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        address = TypeAdapter(Address).validate_python(args.address)
        mandate = Mandate.model_validate_json(args.mandate.read_text()) if args.mandate else None
        store = Store(args.db) if args.db else None
        chain = 43113 if args.mode == "FUJI" else 31337
        version = store.history_version(chain, address, args.mode) if store else 0
        value = PortfolioReader(args.mode, args.rpc_url).collect(
            address, mandate=mandate, history_version=version
        )
        if store:
            store.save_snapshot(value)
        data = value.model_dump_json(indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(data, encoding="utf-8")
        print(data, end="")
    except ControlError as error:
        parser.exit(1, error.code + "\n")
    except (ValidationError, OSError, ValueError):
        parser.exit(1, "INVALID_OBSERVER_INPUT\n")


if __name__ == "__main__":
    main()
