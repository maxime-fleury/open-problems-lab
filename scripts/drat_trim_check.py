#!/usr/bin/env python3
"""Check every stored DRAT trace with an *external* checker: drat-trim.

`oplab.drat` is this repository's own judge, so a bug in it would be invisible
from the inside — a trace would be accepted, stored, and re-accepted by the same
code in every later run.  This script removes that circularity for the artifacts
that are actually on disk: for every certificate that records a trace it rebuilds
the CNF the certificate declares — the circulant encoding of its `(n, sizes)`, or
the class encoding of its group, whichever family it names — decompresses the
stored trace, and hands the pair to `drat-trim` (Marijn Heule's checker, the reference
implementation of the format), which knows nothing about this repository.

It is the same evidence `oplab verify --deep` produces, from an unrelated
implementation, and it runs in CI (the `drat-trim` job) — so the proofs rest on
two checkers that have to agree, plus the Lean layer for the arithmetic rows.

Usage:

    python scripts/drat_trim_check.py                     # drat-trim from PATH
    python scripts/drat_trim_check.py --drat-trim /tmp/drat-trim/drat-trim
    python scripts/drat_trim_check.py --only k18 k55      # a subset, by tag

Exit codes: 0 when every stored trace is verified, 1 when a checker disagrees
(about a digest as well as a trace: a certificate whose file does not match its
recorded sha256 is a failure), 2 when there is nothing to check or the external
checker is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from oplab import drat as DRAT  # noqa: E402
from oplab.verify import declared_instance  # noqa: E402

#: drat-trim prints this line, last, when it accepts the trace
VERIFIED = "s VERIFIED"


def wsl_path(path: Path) -> str:
    """``D:\\gen\\x`` as ``/mnt/d/gen/x``: for a Linux checker under WSL.

    Only a development convenience on Windows — CI runs drat-trim natively and
    passes the paths unchanged.
    """
    text = str(path)
    drive, rest = os.path.splitdrive(text)
    if not drive:
        return text
    return "/mnt/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def certificates(certs_root: Path, only: list[str]) -> list[Path]:
    """Every certificate that records a DRAT trace, in a stable order."""
    found = []
    for path in sorted(certs_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8")).get("payload", {})
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("proof"):
            tag = path.stem
            if only and not any(tag == want or tag.startswith(want) for want in only):
                continue
            found.append(path)
    return found


def prepare(cert_path: Path, workdir: Path) -> dict:
    """Rebuild the CNF and decompress the trace a certificate names.

    The CNF is *rebuilt* rather than read from a stored file, so a trace can only
    be verified against the encoding its own certificate declares — the same
    guarantee the in-repo checker gives.  Which encoding that is comes from the
    certificate's ``problem`` field (``declared_instance``): a
    ``circulant_multicolour`` row is the circulant encoding of ``(n, sizes)``, and a
    ``cayley_multicolour`` row is the class encoding of its *group*, whose clauses
    are a different CNF.  The trace is handed over with its compression removed and
    its encoding intact (a ``.bdrat`` trace is passed to drat-trim as binary DRAT,
    with ``-i``), so the external checker reads the stored artifact rather than a
    conversion of it.
    """
    cert = json.loads(cert_path.read_text(encoding="utf-8"))
    proof = cert["payload"]["proof"]
    instance = declared_instance(cert)
    stored = cert_path.parent / proof["file"]
    inner = ".bdrat" if DRAT.is_binary(stored) else ".drat"
    cnf_path = workdir / f"{cert_path.stem}.cnf"
    proof_path = workdir / f"{cert_path.stem}{inner}"
    instance.write_dimacs(cnf_path, comment=f"{cert_path.name} rebuilt by drat_trim_check.py")
    # the external checker gets the artifact as it is stored, only with the
    # compression removed: what it reads is exactly what the repository carries
    with DRAT.open_proof(stored, "rb") as source, open(proof_path, "wb") as target:
        shutil.copyfileobj(source, target)
    lines = DRAT.read_proof(proof_path)
    digest = DRAT.proof_digest(lines)
    return {
        "tag": cert_path.stem,
        "cnf": cnf_path,
        "proof": proof_path,
        "binary": DRAT.is_binary(stored),
        "steps": len(lines),
        "bytes": proof_path.stat().st_size,
        "sha256": digest,
        "recorded_sha256": proof.get("sha256"),
        "recorded_steps": int(proof.get("steps", -1)),
        "file_sha256": hashlib.sha256(stored.read_bytes()).hexdigest(),
        "recorded_file_sha256": proof.get("file_sha256"),
    }


def split_command(text: str) -> list[str]:
    """Split ``--drat-trim`` into argv without mangling a path.

    ``shlex.split`` unquotes POSIX-style, which eats the backslashes of
    ``C:\\tools\\drat-trim.exe`` (and then reports the checker missing); an argument
    that names an existing file is therefore taken literally.
    """
    if Path(text).exists():
        return [text]
    return shlex.split(text)


def read_pin(path: Path) -> dict:
    """Parse ``drat-trim.pin``: ``commit``, ``source`` and ``sha256`` lines."""
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(" ")
        fields[key] = value.strip()
    return fields


def source_digest(path: str, through_wsl: bool) -> str | None:
    """sha256 of the checker's source, read here or through WSL; None if absent.

    A path that does not exist locally is read through ``wsl`` when the checker
    itself runs there, since the source then lives on the other side.
    """
    local = Path(path)
    if local.exists():
        return hashlib.sha256(local.read_bytes()).hexdigest()
    if through_wsl:
        proc = subprocess.run(["wsl", "-e", "bash", "-lc", f"sha256sum {shlex.quote(path)}"],
                              capture_output=True, text=True, errors="replace")
        if proc.returncode == 0 and proc.stdout.split():
            return proc.stdout.split()[0]
    return None


def check_pin(command: list[str], args) -> tuple[dict, str, str | None]:
    """Confine the run to the pinned checker; the third value is its source hash.

    A source file whose hash disagrees with the pin is a hard failure, before any
    trace is judged: otherwise the verdict would quietly come from a checker the
    repository never pinned.  ``commit``/``sha256`` are reported either way.
    """
    pin_path = Path(args.pin) if args.pin else ROOT / "scripts" / "drat-trim.pin"
    if not pin_path.exists():
        if args.require_pin:
            raise SystemExit(f"{pin_path} is missing: the external checker is not pinned")
        print(f"warning: {pin_path} not found, so the checker is unpinned", file=sys.stderr)
        return {}, str(pin_path), None
    pin = read_pin(pin_path)
    source = args.source
    if source is None and len(command) == 1:
        beside = Path(shutil.which(command[0]) or "").parent / pin.get("source", "drat-trim.c")
        source = str(beside) if beside.exists() else None
    digest = source_digest(source, args.wsl) if source else None
    if digest is None:
        message = (f"{pin_path} pins {pin.get('source', 'drat-trim.c')} at "
                   f"{pin.get('sha256', '?')[:16]}… but no source file was found "
                   f"(pass --source PATH)")
        if args.require_pin:
            raise SystemExit(message)
        print(f"warning: {message}", file=sys.stderr)
        return pin, str(pin_path), None
    if pin.get("sha256") and digest != pin["sha256"]:
        raise SystemExit(
            f"PIN MISMATCH: the checker's source hashes to {digest[:16]}…, but "
            f"{pin_path} pins {pin['sha256'][:16]}… (commit {pin.get('commit', '?')[:12]}).\n"
            f"Refusing to judge the proofs with an unpinned checker; to accept the "
            f"new one, re-run it over the whole store and update the pin.")
    return pin, str(pin_path), digest


def run_checker(command: list[str], prepared: dict, translate: bool) -> dict:
    cnf = wsl_path(prepared["cnf"]) if translate else str(prepared["cnf"])
    proof = wsl_path(prepared["proof"]) if translate else str(prepared["proof"])
    # -i is drat-trim's "the proof is binary DRAT" switch; without it, a binary
    # trace is misread as text and every line fails
    flags = ["-i"] if prepared["binary"] else []
    started = time.time()
    proc = subprocess.run([*command, cnf, proof, *flags], capture_output=True, text=True,
                          errors="replace")
    seconds = time.time() - started
    output = proc.stdout + proc.stderr
    if proc.returncode != 0 and VERIFIED in output:
        # drat-trim returns 0 when it verifies; anything else is a disagreement
        # worth reporting rather than rounding
        return {"ok": False, "seconds": seconds, "returncode": proc.returncode,
                "detail": f"exit status {proc.returncode}", "output": output}
    if VERIFIED not in output:
        detail = next((line for line in output.splitlines()
                       if "ERROR" in line or "NOT VERIFIED" in line or line.startswith("s ")),
                      "no 's VERIFIED' in the output")
        return {"ok": False, "seconds": seconds, "returncode": proc.returncode,
                "detail": detail, "output": output}
    return {"ok": True, "seconds": seconds, "returncode": proc.returncode,
            "detail": "", "output": output}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--certs", default=str(ROOT / "certs"), help="certificate root")
    parser.add_argument("--drat-trim", default="drat-trim",
                        help="the external checker, with arguments if it needs them")
    parser.add_argument("--only", nargs="*", default=[],
                        help="limit to these certificate tags (prefixes are accepted)")
    parser.add_argument("--workdir", default=None,
                        help="where to rebuild the CNF and trace files (default: a temp dir)")
    parser.add_argument("--wsl", action="store_true",
                        help="hand the checker WSL paths (/mnt/d/...) instead of Windows ones")
    parser.add_argument("--pin", default=None,
                        help="the pin file (default: scripts/drat-trim.pin)")
    parser.add_argument("--source", default=None,
                        help="the checker's source, to hash against the pin "
                             "(default: <the binary's directory>/drat-trim.c)")
    parser.add_argument("--require-pin", action="store_true",
                        help="fail when the checker's source cannot be hashed "
                             "(CI passes this); a wrong hash fails either way")
    parser.add_argument("--keep", action="store_true", help="keep the rebuilt files in --workdir")
    args = parser.parse_args(argv)

    command = split_command(args.drat_trim)
    if not command:
        print("no external checker given", file=sys.stderr)
        return 2
    resolved = shutil.which(command[0])
    if resolved is None and not (len(command) > 1 and command[0].lower() == "wsl"):
        print(f"{command[0]}: not found (build drat-trim, or pass --drat-trim PATH)",
              file=sys.stderr)
        return 2

    pin, pin_path, source_hash = check_pin(command, args)

    certs = certificates(Path(args.certs), args.only)
    if not certs:
        print(f"no certificate under {args.certs} records a DRAT trace", file=sys.stderr)
        return 2

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="drat-trim-"))
    workdir.mkdir(parents=True, exist_ok=True)
    # drat-trim answers -h with its usage text, so the binary's own name is the
    # better identity when nothing else in the banner is identifiable
    banner = subprocess.run([*command, "-h"], capture_output=True, text=True, errors="replace")
    header = next((line.strip() for line in (banner.stdout + banner.stderr).splitlines()
                   if "drat-trim" in line and "[" not in line), command[-1])
    print(f"external checker: {header}  ({args.drat_trim})")
    identity = f"pinned at {pin.get('commit', '?')[:12]}" if pin else "UNPINNED"
    if source_hash:
        identity += f", source sha256 {source_hash[:16]}…"
    print(f"pin: {pin_path}  {identity}")
    print(f"{len(certs)} stored traces to cross-check, rebuilt CNFs in {workdir}")

    failures = 0
    width = max(len(path.stem) for path in certs)
    for cert_path in certs:
        prepared = prepare(cert_path, workdir)
        if prepared["sha256"] != prepared["recorded_sha256"]:
            print(f"{prepared['tag']:<{width}}  DIGEST MISMATCH: the stored trace is not the "
                  f"one this certificate claims")
            failures += 1
            continue
        if prepared["steps"] != prepared["recorded_steps"]:
            print(f"{prepared['tag']:<{width}}  STEP COUNT MISMATCH: {prepared['steps']} lines "
                  f"on disk, {prepared['recorded_steps']} recorded")
            failures += 1
            continue
        recorded_file = prepared["recorded_file_sha256"]
        if recorded_file is not None and prepared["file_sha256"] != recorded_file:
            print(f"{prepared['tag']:<{width}}  FILE DIGEST MISMATCH: the stored bytes are not "
                  f"the ones this certificate records")
            failures += 1
            continue
        result = run_checker(command, prepared, args.wsl)
        verdict = "VERIFIED" if result["ok"] else f"REJECTED ({result['detail']})"
        print(f"{prepared['tag']:<{width}}  {prepared['steps']:>7} steps "
              f"{prepared['bytes'] / 1e6:>7.1f} MB  {verdict}  [{result['seconds']:.1f} s]")
        if not result["ok"]:
            failures += 1
            print("\n".join("    " + line for line in result["output"].splitlines()[-5:]))
    if not args.keep and not args.workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    checker = f"{command[-1]}" + (f" at {pin.get('commit', '?')[:12]}" if pin else " (unpinned)")
    print(f"{len(certs) - failures}/{len(certs)} traces verified by {checker}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
