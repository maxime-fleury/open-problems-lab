#!/usr/bin/env python3
"""Time both replayers on every stored trace: the in-repo checker and drat-trim.

Every proof in `certs/` is replayed by `oplab.drat`, the repository's own judge —
about four hundred lines, no solver, no dependency.  It is also slow: a trace of a
few hundred thousand steps costs minutes, which is why an `unsat` row left behind
by a 300-second CDCL run (tens of millions of steps) is not storable at all today.
`drat-trim`, the reference implementation of the format, is two orders of magnitude
faster on the same input, and this script is how much faster *here*, on the traces
that are actually committed, rather than in a claim.

Nothing is decided by this script.  For each certificate that records a trace it
rebuilds the CNF the certificate declares (through `drat_trim_check.prepare`, so it
is the same rebuild the cross-check uses), then times

  * `oplab.drat.check_proof` — the in-repo judge, pure Python, no solver;
  * `drat-trim` — the pinned external judge, on the same CNF and the same trace;

and prints steps, both times and the ratio.  The Python column is *measured* here,
not read from the certificates: the recorded `replay_seconds` was taken when the
trace was stored, and comparing two checkers on two machines would not be a
comparison.

Usage:

    python scripts/replay_bench.py                                   # drat-trim on PATH
    python scripts/replay_bench.py --drat-trim "wsl -e /home/me/drat-trim/drat-trim" --wsl
    python scripts/replay_bench.py --only k50 --skip-python          # the native side alone
    python scripts/replay_bench.py --json runs/replay_bench.json

Exit codes: 0 when every timed run agreed with its certificate, 1 when a replayer
disagreed (a disagreement is a failure, whatever the clock says), 2 when there is
nothing to time or the external checker is missing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from oplab import drat as DRAT  # noqa: E402
from oplab.verify import declared_instance  # noqa: E402
import drat_trim_check as DTC  # noqa: E402


def python_replay(prepared: dict) -> dict:
    """Time the in-repo checker on the rebuilt CNF and the decompressed trace."""
    cert = json.loads(prepared["cert_path"].read_text(encoding="utf-8"))
    instance = declared_instance(cert)
    clauses = list(instance.clauses())
    lines = DRAT.read_proof(prepared["proof"])
    started = time.time()
    result = DRAT.check_proof(instance.total_vars(), clauses, lines)
    seconds = time.time() - started
    return {
        "ok": bool(result["ok"]),
        "seconds": seconds,
        "reason": result.get("reason", ""),
        "num_vars": instance.total_vars(),
        "num_clauses": len(clauses),
        "steps_checker_read": result.get("steps", len(lines)),
    }


def digest_agrees(prepared: dict) -> str | None:
    """The same three digest checks the cross-check makes, as a reason or ``None``.

    A replayer is being timed, not a certificate, but a trace whose digests do not
    match the certificate that cites it must not be timed either: the number would
    describe a trace no certificate in this repository claims.
    """
    if prepared["sha256"] != prepared["recorded_sha256"]:
        return "the stored trace is not the one this certificate claims"
    if prepared["steps"] != prepared["recorded_steps"]:
        return (f"{prepared['steps']} lines on disk, "
                f"{prepared['recorded_steps']} recorded")
    recorded_file = prepared["recorded_file_sha256"]
    if recorded_file is not None and prepared["file_sha256"] != recorded_file:
        return "the stored bytes are not the ones this certificate records"
    return None


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
    parser.add_argument("--pin", default=None, help="the pin file (default: scripts/drat-trim.pin)")
    parser.add_argument("--source", default=None,
                        help="the checker's source, to hash against the pin")
    parser.add_argument("--require-pin", action="store_true",
                        help="fail when the checker's source cannot be hashed")
    parser.add_argument("--skip-python", action="store_true",
                        help="time only the external checker: for a trace the slow one "
                             "cannot afford at all")
    parser.add_argument("--skip-native", action="store_true",
                        help="time only the in-repo checker: a baseline needs no checker")
    parser.add_argument("--json", default=None, help="write the rows here")
    parser.add_argument("--keep", action="store_true", help="keep the rebuilt files")
    args = parser.parse_args(argv)
    if args.skip_native and args.skip_python:
        print("both replayers skipped: there is nothing to time", file=sys.stderr)
        return 2

    command = DTC.split_command(args.drat_trim) if not args.skip_native else []
    pin, pin_path, source_hash = {}, "", None
    if command:
        if shutil.which(command[0]) is None and not (len(command) > 1
                                                     and command[0].lower() == "wsl"):
            print(f"{command[0]}: not found (build drat-trim, or pass --drat-trim PATH)",
                  file=sys.stderr)
            return 2
        pin, pin_path, source_hash = DTC.check_pin(command, args)

    certs = DTC.certificates(Path(args.certs), args.only)
    if not certs:
        print(f"no certificate under {args.certs} records a DRAT trace", file=sys.stderr)
        return 2

    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="replay-bench-"))
    workdir.mkdir(parents=True, exist_ok=True)
    judge = command[-1] if command else "(native side skipped)"
    if pin:
        judge += f" pinned at {pin.get('commit', '?')[:12]}"
        if source_hash:
            judge += f", source sha256 {source_hash[:16]}…"
    print(f"judges: oplab.drat (Python) and {judge}")
    print(f"{len(certs)} stored traces, rebuilt CNFs in {workdir}")

    rows: list[dict] = []
    failures = 0
    width = max(len(path.stem) for path in certs)
    for cert_path in certs:
        prepared = DTC.prepare(cert_path, workdir)
        prepared["cert_path"] = cert_path
        reason = digest_agrees(prepared)
        if reason is not None:
            print(f"{prepared['tag']:<{width}}  REFUSED: {reason}")
            failures += 1
            continue
        row: dict = {"tag": prepared["tag"], "steps": prepared["steps"],
                     "bytes": prepared["bytes"], "binary": prepared["binary"]}
        if not args.skip_python:
            fast = python_replay(prepared)
            row["python"] = fast
            if not fast["ok"]:
                failures += 1
        if command:
            native = DTC.run_checker(command, prepared, args.wsl)
            row["native"] = {"ok": native["ok"], "seconds": native["seconds"],
                             "detail": native.get("detail", "")}
            if not native["ok"]:
                failures += 1
        rows.append(row)
        cell = (f"{row['python']['seconds']:>9.1f} s" if not args.skip_python else f"{'-':>9}")
        native_cell = (f"{row['native']['seconds']:>8.2f} s" if command else f"{'-':>8}")
        ratio = ""
        if not args.skip_python and command:
            ratio = f"  x{row['python']['seconds'] / max(row['native']['seconds'], 1e-6):>8.1f}"
        verdict = "ok" if all(part.get("ok", True) for part in (row.get("python", {}),
                                                                row.get("native", {}))) else "MISMATCH"
        print(f"{prepared['tag']:<{width}}  {prepared['steps']:>8} steps "
              f"{prepared['bytes'] / 1e6:>7.1f} MB  python {cell}  native {native_cell}"
              f"{ratio}  {verdict}", flush=True)

    if not args.keep and not args.workdir:
        shutil.rmtree(workdir, ignore_errors=True)

    steps = sum(row["steps"] for row in rows)
    if rows and not args.skip_python:
        seconds = sum(row["python"]["seconds"] for row in rows)
        print(f"\nin-repo: {steps} steps in {seconds:.1f} s "
              f"({steps / max(seconds, 1e-9):.0f} steps/s over {len(rows)} traces)")
    if rows and command:
        native_seconds = sum(row["native"]["seconds"] for row in rows)
        print(f"native : {steps} steps in {native_seconds:.1f} s "
              f"({steps / max(native_seconds, 1e-9):.0f} steps/s over {len(rows)} traces)")
        if not args.skip_python:
            python_seconds = sum(row["python"]["seconds"] for row in rows)
            print(f"ratio  : {python_seconds / max(native_seconds, 1e-9):.0f}x faster "
                  f"end to end, on the same CNFs and traces")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"rows": rows, "what": "both replayers timed on every stored trace",
             "judge": judge,
             "pin": str(pin_path) if pin_path else None,
             "source_sha256": source_hash}, indent=2) + "\n", encoding="utf-8")
        print(f"rows written to {args.json}")
    both = command and not args.skip_python
    tail = " with both replayers agreeing" if both else ""
    print(f"{len(rows) - failures}/{len(rows)} traces timed{tail}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
