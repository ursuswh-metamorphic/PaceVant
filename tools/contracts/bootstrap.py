"""Install pinned Solidity sources without npm. Does not read .env or deploy."""

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "5fd1781b1454fd1ef8e722282f86f9293cacf256"
ARCHIVE_SHA256 = "6542272013ef3322d86f1eb6b47fc94ae1a95992169a5b3e160af189989187a4"
URL = f"https://codeload.github.com/OpenZeppelin/openzeppelin-contracts/tar.gz/{COMMIT}"


def install_contracts(root=ROOT):
    destination = root / "lib/openzeppelin-contracts"
    marker = destination / ".treasury-source.json"
    expected = {"version": "5.6.1", "commit": COMMIT, "archive_sha256": ARCHIVE_SHA256}
    if destination.exists():
        if marker.is_file() and json.loads(marker.read_text()) == expected:
            return {"dependency": "OpenZeppelin", "status": "ALREADY_INSTALLED", **expected}
        raise RuntimeError(
            "Existing lib/openzeppelin-contracts is unrecognized; preserve/review it before installing"
        )
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("OpenZeppelin source archive failed SHA-256 verification")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openzeppelin-", dir=destination.parent) as temporary:
        extracted = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    raise RuntimeError("Unexpected OpenZeppelin archive entry")
            archive.extractall(extracted, filter="data")
        source = extracted / f"openzeppelin-contracts-{COMMIT}"
        if not (source / "contracts/token/ERC20/ERC20.sol").is_file():
            raise RuntimeError("OpenZeppelin archive layout mismatch")
        (source / marker.name).write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        shutil.move(str(source), str(destination))
    return {"dependency": "OpenZeppelin", "status": "INSTALLED", **expected}


if __name__ == "__main__":
    print(json.dumps(install_contracts(), indent=2))
