import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from treasury_backend.paths import ROOT
from treasury_contracts.toolchain import foundry_binary

from .errors import OpsError


def compile_contracts(root=ROOT):
    subprocess.run(
        [foundry_binary("forge", ROOT), "build", "--root", str(root)],
        cwd=ROOT,
        check=True,
    )


def execution_python():
    """Both runtime roles use the same locked backend environment."""
    return sys.executable


def check_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise OpsError(
                f"Port {port} is in use; choose another TREASURY_A_PORT/TREASURY_B_PORT"
            ) from None


def stop_process(proc):
    if proc.poll() is None:
        if os.name == "nt":
            # uv's Windows venv launcher owns an interpreter child. Kill only this
            # Popen subtree; terminating the launcher alone leaks the API/Anvil.
            subprocess.run(
                [str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                 "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=5)
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def anvil_binary(root=ROOT):
    return foundry_binary("anvil", root)


@contextmanager
def local_chain(p):
    if p.network != "local":
        yield
        return
    w3 = p.web3()
    proc = None
    try:
        if not w3.is_connected():
            u = urlsplit(p.rpc)
            p.control_data.mkdir(parents=True, exist_ok=True)
            with (p.control_data / "anvil.log").open("a", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    [
                        anvil_binary(),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(u.port or 8545),
                        "--chain-id",
                        "31337",
                        "--hardfork",
                        "cancun",
                        "--silent",
                    ],
                    stdout=log,
                    stderr=log,
                )
            for _ in range(100):
                if w3.is_connected():
                    break
                if proc.poll() is not None:
                    raise OpsError("Anvil startup failed")
                time.sleep(0.1)
            else:
                raise OpsError("Anvil startup timed out")
        if not w3.client_version.lower().startswith("anvil") or w3.eth.chain_id != 31337:
            raise OpsError("Local target is not Anvil chain 31337")
        # The oracle heartbeat mines a fresh LOCAL block every five seconds;
        # no persistent mining configuration of an existing user node is changed.
        yield
    finally:
        if proc:
            stop_process(proc)


def wait_ready(proc, url):
    for _ in range(200):
        if proc.poll() is not None:
            raise OpsError("Service exited; inspect the private profile log directory")
        try:
            if httpx.get(url, timeout=0.4, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise OpsError("Service readiness timed out")
