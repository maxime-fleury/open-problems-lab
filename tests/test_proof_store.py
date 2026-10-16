"""Pin the proof store and the external checker, so neither drifts quietly.

Every other check in the repository answers "is this trace valid?"  These answer a
different question: "is this the trace, and the checker, that the repository
decided to stand behind?"  A valid proof can still be the *wrong* proof — re-solve
an instance, get a different trace, write a fresh certificate with fresh digests
and every test in the suite still passes while the reviewed artifact has been
replaced.  `certs/circulant_multicolour/MANIFEST.txt` closes that gap by listing
what the store is supposed to contain, and `scripts/drat-trim.pin` does the same
for the third-party checker CI builds and trusts.

`scripts/proof_manifest.py --check` is what CI runs; these tests exercise the same
CLI, including the tampering cases, on a throwaway copy of one certificate so they
stay fast no matter how large the real traces get.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCRIPT = ROOT / "scripts" / "proof_manifest.py"
CROSS_CHECK = ROOT / "scripts" / "drat_trim_check.py"
PIN = ROOT / "scripts" / "drat-trim.pin"
CERT_DIR = ROOT / "certs" / "circulant_multicolour"
MANIFEST = CERT_DIR / "MANIFEST.txt"


def _manifest(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(MANIFEST_SCRIPT), *args],
                          capture_output=True, text=True)


def _cross_check(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CROSS_CHECK), *args],
                          capture_output=True, text=True)


def _one_certificate_store(root: Path) -> Path:
    """A store holding exactly one real certificate and its real trace."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "proofs").mkdir(exist_ok=True)
    cert = json.loads((CERT_DIR / "k18_4x4.json").read_text(encoding="utf-8"))
    trace = Path(cert["payload"]["proof"]["file"]).name
    shutil.copyfile(CERT_DIR / "proofs" / trace, root / "proofs" / trace)
    (root / "k18_4x4.json").write_text(json.dumps(cert, indent=2), encoding="utf-8")
    return root


#: every committed proof store: its directory, and how many traces it pins
STORES = {
    CERT_DIR: 9,
    ROOT / "certs" / "cayley": 3,
}


def _pinned(root: Path) -> int:
    """The number of trace rows a manifest lists (its header starts with ``#``)."""
    lines = (root / "MANIFEST.txt").read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines if line.strip() and not line.startswith("#"))


def test_the_committed_stores_match_their_manifests():
    """Each manifest, its certificates and the bytes on disk all agree.

    Two stores are pinned, because two kinds record traces and they are different
    families: the circulant rows and the group rows.  A manifest only speaks for its
    own directory, so both are checked, and the counts are asserted here rather than
    read off the manifests, which is what makes a dropped or added trace a failure.
    """
    for root, expected in STORES.items():
        result = _manifest("--certs", str(root), "--check")
        assert result.returncode == 0, f"{root}: {result.stdout}{result.stderr}"
        assert "digests match" in result.stdout, result.stdout
        assert _pinned(root) == expected, f"{root}: {_pinned(root)} traces pinned"


def test_a_changed_trace_fails_the_manifest_check(tmp_path):
    """One flipped byte in a stored trace is a loud failure, not a re-digest."""
    root = _one_certificate_store(tmp_path / "certs")
    wrote = _manifest("--certs", str(root), "--write")
    assert wrote.returncode == 0, wrote.stdout + wrote.stderr
    assert _manifest("--certs", str(root), "--check").returncode == 0

    trace = root / "proofs" / "k18_4x4.bdrat.xz"
    payload = bytearray(trace.read_bytes())
    payload[len(payload) // 2] ^= 0x01
    trace.write_bytes(bytes(payload))

    result = _manifest("--certs", str(root), "--check")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "the bytes on disk hash to" in result.stderr, result.stderr
    assert "without updating the manifest" in result.stderr, result.stderr


def test_a_reesolved_certificate_fails_the_manifest_check(tmp_path):
    """New digests in the certificate do not buy a pass: the pin is the manifest's."""
    root = _one_certificate_store(tmp_path / "certs")
    assert _manifest("--certs", str(root), "--write").returncode == 0

    cert_path = root / "k18_4x4.json"
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    proof = cert["payload"]["proof"]
    proof["sha256"] = "0" * 64
    proof["steps"] = int(proof["steps"]) + 1
    cert_path.write_text(json.dumps(cert, indent=2), encoding="utf-8")

    result = _manifest("--certs", str(root), "--check")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "the certificate's text sha256 is" in result.stderr, result.stderr
    assert "steps recorded" in result.stderr, result.stderr


def test_a_dropped_trace_or_manifest_is_loud(tmp_path):
    """A trace that is recorded but absent, and a store with no manifest, both fail."""
    root = _one_certificate_store(tmp_path / "certs")
    assert _manifest("--certs", str(root), "--write").returncode == 0

    (root / "MANIFEST.txt").unlink()
    result = _manifest("--certs", str(root), "--check")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "nothing is pinned" in result.stderr, result.stderr

    assert _manifest("--certs", str(root), "--write").returncode == 0
    (root / "proofs" / "k18_4x4.bdrat.xz").unlink()
    result = _manifest("--certs", str(root), "--check")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "not on disk" in result.stderr, result.stderr
    # and it refuses to pin a store whose bytes are missing
    assert _manifest("--certs", str(root), "--write").returncode == 2


def test_an_empty_store_is_an_error_not_a_pass(tmp_path):
    """Nothing to pin is exit 2, so a broken path cannot look like a clean store."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _manifest("--certs", str(empty), "--check")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no certificate" in result.stderr, result.stderr
    assert _manifest("--certs", str(empty), "--write").returncode == 2


def test_the_pin_file_names_a_commit_and_a_source_hash():
    """The pin is parseable, and specific enough to identify one source file."""
    fields = {}
    for line in PIN.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            fields[key] = value.strip()
    assert re.fullmatch(r"[0-9a-f]{40}", fields["commit"]), fields
    assert re.fullmatch(r"[0-9a-f]{64}", fields["sha256"]), fields
    assert fields["source"].endswith(".c"), fields
    assert "2e3b2dc0ecf938addbd779d42877b6ed69d9a985" == fields["commit"], (
        "the pin moved: check whether the new drat-trim agrees on every stored trace")


def test_an_unpinned_checker_source_is_refused(tmp_path):
    """A checker whose source is not the pinned one is a hard failure."""
    other = tmp_path / "drat-trim.c"
    other.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    result = _cross_check("--drat-trim", sys.executable, "--source", str(other))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PIN MISMATCH" in result.stderr, result.stderr
    assert "Refusing to judge the proofs" in result.stderr, result.stderr


def test_a_missing_pin_is_loud_when_it_is_required(tmp_path):
    """CI asks for the pin; a vanished pin file must not slip through as unknown."""
    missing = tmp_path / "not-a-pin"
    empty = tmp_path / "no-certs"
    empty.mkdir()
    soft = _cross_check("--drat-trim", sys.executable, "--pin", str(missing),
                        "--certs", str(empty))
    assert soft.returncode == 2, soft.stdout + soft.stderr
    assert "not found" in soft.stderr, soft.stderr

    strict = _cross_check("--drat-trim", sys.executable, "--pin", str(missing),
                          "--require-pin", "--certs", str(empty))
    assert strict.returncode == 1, strict.stdout + strict.stderr
    assert "not pinned" in strict.stderr, strict.stderr


def test_the_required_pin_accepts_the_real_source_when_it_is_here(tmp_path):
    """Where a real drat-trim source is available, --require-pin must accept it.

    The checker is found the way `tests/test_drat_trim.py` finds it — on `PATH`, or
    wherever `OPLAB_DRAT_TRIM` points, including a build inside WSL, whose source is
    then named by `OPLAB_DRAT_TRIM_SOURCE` (a WSL path, with `OPLAB_DRAT_TRIM_WSL=1`
    for the file arguments).  CI's `drat-trim` job runs exactly this command against
    the source it just compiled; without a checker the test skips rather than pass.
    """
    checker = os.environ.get("OPLAB_DRAT_TRIM")
    source = os.environ.get("OPLAB_DRAT_TRIM_SOURCE")
    if checker is None:
        binary = shutil.which("drat-trim")
        if binary is None:
            pytest.skip("no drat-trim here (CI's drat-trim job runs this command)")
        checker = binary
        source = source or str(Path(binary).parent / "drat-trim.c")
    elif source is None:
        pytest.skip("set OPLAB_DRAT_TRIM_SOURCE to the source of the checker in OPLAB_DRAT_TRIM")
    empty = tmp_path / "no-certs"
    empty.mkdir()
    args = ["--drat-trim", checker, "--source", source, "--require-pin", "--certs", str(empty)]
    if os.environ.get("OPLAB_DRAT_TRIM_WSL") == "1":
        args.append("--wsl")
    result = _cross_check(*args)
    # the store is deliberately bogus: what matters is that the pin was accepted and
    # the run got past it, to the complaint about the certificates
    assert "PIN MISMATCH" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert "records a DRAT trace" in result.stderr, result.stderr
