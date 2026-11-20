from types import SimpleNamespace

import pytest
from eth_account import Account
from web3 import Web3
from web3.exceptions import TransactionNotFound

from treasury_backend.operations.errors import OpsError
from treasury_backend.operations.owner_transactions import send_owner_transaction


def test_rpc_timeout_resumes_same_signed_owner_transaction(tmp_path):
    account = Account.create()
    p = SimpleNamespace(control_data=tmp_path, chain_id=43113)

    class Eth:
        chain_id = 43113
        broadcasts = []
        waits = 0

        def get_transaction(self, hash_):
            if not self.broadcasts:
                raise TransactionNotFound("Not found")
            assert Web3.to_hex(Web3.keccak(self.broadcasts[0])) == hash_
            return {}

        def send_raw_transaction(self, raw):
            self.broadcasts.append(raw)

        def wait_for_transaction_receipt(self, hash_, timeout):
            self.waits += 1
            if self.waits == 1:
                raise TimeoutError()
            return SimpleNamespace(status=1, blockNumber=123)

    eth = Eth()
    w3 = SimpleNamespace(eth=eth)

    def build():
        return {
            "from": account.address,
            "chainId": 43113,
            "to": account.address,
            "nonce": 0,
            "value": 0,
            "gas": 21000,
            "gasPrice": 1,
        }

    with pytest.raises(OpsError, match="outcome unknown"):
        send_owner_transaction(p, w3, account, "a" * 64, "create-session", build)
    result = send_owner_transaction(
        p,
        w3,
        account,
        "a" * 64,
        "create-session",
        lambda: pytest.fail("Must not build another owner transaction"),
    )
    assert result["block"] == 123 and len(eth.broadcasts) == 1


def test_wrong_owner_chain_is_rejected_before_signing(tmp_path):
    with pytest.raises(OpsError, match="chain mismatch"):
        send_owner_transaction(
            SimpleNamespace(control_data=tmp_path, chain_id=43113),
            SimpleNamespace(eth=SimpleNamespace(chain_id=1)),
            Account.create(),
            "a" * 64,
            "create-session",
            lambda: pytest.fail("No signing"),
        )
