"""Cross-check the stored DRAT traces with an *external* checker.

The repository's own checker is the trusted base for the proof-carrying `unsat`
rows, which means everything about them is decided by one program: a bug in
`oplab/drat.py` would accept a trace, the certificate would store it, and every
later run would accept it again with the same code.  These tests open that loop
from the outside by running `scripts/drat_trim_check.py`, which rebuilds each CNF
from the certificate and hands the pair to `drat-trim` — the reference checker
for the format, which knows nothing about this repository.

drat-trim is not vendored and not required: without it these tests skip, and CI
builds it from a pinned commit in the `drat-trim` job.  A Windows development
machine can point at a build elsewhere, including one inside WSL:

    OPLAB_DRAT_TRIM="wsl -e /home/you/drat-trim/drat-trim" \\
    OPLAB_DRAT_TRIM_WSL=1 python -m pytest tests/test_drat_trim.py -q

The two tampering cases are the ones that matter: an edited trace that the
certificate's own digest still catches, and a *forged* certificate whose digest
was rewritten to match — which only the external checker can refuse.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from oplab import drat as DRAT
from oplab.verify import payload_hash

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "drat_trim_check.py"
CERT_DIR = ROOT / "certs" / "circulant_multicolour"

#: the external checker, as a command line; see the module docstring
CHECKER = os.environ.get("OPLAB_DRAT_TRIM", "drat-trim")
UNDER_WSL = os.environ.get("OPLAB_DRAT_TRIM_WSL") == "1"


def _available() -> bool:
    first = (CHECKER.split() or [""])[0]
    return bool(shutil.which(first)) or first.lower() == "wsl"


needs_drat_trim = pytest.mark.skipif(
    not _available(), reason="no external drat-trim (set OPLAB_DRAT_TRIM to point at one)")


def _run(*args: str) -> subprocess.CompletedProcess:
    command = [sys.executable, str(SCRIPT), "--drat-trim", CHECKER]
    if UNDER_WSL:
        command.append("--wsl")
    return subprocess.run([*command, *args], capture_output=True, text=True)


def _tampered_certificate(root: Path, *, forge_digest: bool) -> Path:
    """Copy the K18 certificate and give it a trace with an unjustified empty clause.

    With ``forge_digest`` every digest the certificate records is rewritten to match
    the edited trace — the canonical text digest, the file digest, the sizes, the
    counts — and the payload hash with them, which is what a determined edit would
    look like: every check in this repository passes and the external checker has to
    be the one that refuses.
    """
    source = CERT_DIR / "k18_4x4.json"
    cert = json.loads(source.read_text(encoding="utf-8"))
    relative = cert["payload"]["proof"]["file"]
    lines = DRAT.read_proof(source.parent / relative)
    lines.insert(1, "0")
    root.mkdir(parents=True, exist_ok=True)
    (root / "proofs").mkdir(exist_ok=True)
    stored = DRAT.write_proof(root / "proofs" / Path(relative).name, lines)
    proof = cert["payload"]["proof"]
    if forge_digest:
        proof.update({key: stored[key] for key in
                      ("sha256", "file_sha256", "steps", "added", "deleted",
                       "payload_bytes", "stored_bytes", "encoding")})
        cert["payload_sha256"] = payload_hash(cert["payload"])
    (root / source.name).write_text(json.dumps(cert, indent=2), encoding="utf-8")
    return root


@needs_drat_trim
def test_every_stored_trace_passes_the_external_checker():
    """Every stored trace is checked by drat-trim against its own rebuilt CNF.

    Two stores are covered, and they are different families: nine circulant rows and
    three rows over a *group* (`certs/cayley`), whose CNF the script has to rebuild
    from the group description instead of from `(n, sizes)` — so a trace attached to
    the wrong family fails here even though its own digests are intact.
    """
    result = _run()
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if "steps" in line]
    assert len(lines) == 12, result.stdout
    assert all("VERIFIED" in line and "REJECTED" not in line for line in lines), result.stdout
    assert "12/12 traces verified" in result.stdout, result.stdout
    # the two heaviest traces are checked here too: the external checker is fast
    # enough that the rows this repository's Python checker leaves to `--deep` are
    # not special-cased away
    assert "k50_3x3x3x3" in result.stdout and "k55_3x4x4" in result.stdout, result.stdout
    for group_row in ("k18_4x4_D9", "k18_4x4_Z3xD3", "k30_3x3x4_D15"):
        assert group_row in result.stdout, result.stdout


@needs_drat_trim
def test_an_edited_trace_is_caught_before_the_external_checker_runs(tmp_path):
    """A trace that is not the one the certificate names fails the digest check."""
    root = _tampered_certificate(tmp_path / "tampered", forge_digest=False)
    result = _run("--certs", str(root))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DIGEST MISMATCH" in result.stdout, result.stdout
    assert "0/1 traces verified" in result.stdout, result.stdout


@needs_drat_trim
def test_a_forged_certificate_is_rejected_by_the_external_checker(tmp_path):
    """With every recorded digest rewritten, only the external checker can refuse it."""
    root = _tampered_certificate(tmp_path / "forged", forge_digest=True)
    result = _run("--certs", str(root))
    assert result.returncode == 1, result.stdout + result.stderr
    # the script's own checks all pass, so the verdict really comes from drat-trim
    assert "MISMATCH" not in result.stdout, result.stdout
    assert "REJECTED" in result.stdout and "s NOT VERIFIED" in result.stdout, result.stdout
    assert "0/1 traces verified" in result.stdout, result.stdout


@needs_drat_trim
def test_no_stored_trace_is_reported_rather_than_passed(tmp_path):
    """Asking about a directory with no traces is an error, not a vacuous success."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run("--certs", str(empty))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "records a DRAT trace" in result.stderr, result.stderr
