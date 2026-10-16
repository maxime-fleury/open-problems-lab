#!/usr/bin/env python3
"""Pin the proof store, so a change to a trace cannot happen quietly.

Each certificate already records its trace's digest, step count and stored size,
and `oplab verify` re-checks them on every run.  That catches an *edit* — but not
a consistent *regeneration*: re-solve the instance, get a different trace, write a
new certificate with new digests, and every check in the repository still passes
while the artifact everyone reviewed has been replaced.  The same goes for a
stored trace that is quietly dropped, or one that appears without a certificate.

This file is the answer to that: `proofs/MANIFEST.txt` lists every trace that is
supposed to be in the repository, with both its digests (the sha256 of the
canonical *text*, which is what a certificate pins, and the sha256 of the *bytes*
on disk).  The manifest is checked in, so changing what the store contains means
changing it too — a visible diff, in review, rather than a silent one:

    python scripts/proof_manifest.py --check      # what CI runs (exit 1 on drift)
    python scripts/proof_manifest.py --write      # after intentionally re-solving

`--check` compares three things and reports each mismatch by name: the manifest
against the certificates, the manifest against the files on disk, and the set of
traces against the set of certificates.

There is one manifest per store, because there are two kinds that record traces
and they are not the same family: `--certs certs/circulant_multicolour` (the
default) pins the circulant rows, and `--certs certs/cayley` pins the group rows
`oplab cayley` writes.  `make proof-store` checks both.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

MANIFEST_NAME = "MANIFEST.txt"
COLUMNS = ("text_sha256", "file_sha256", "steps", "encoding", "stored_bytes", "file")


def manifest_path(certs_root: Path) -> Path:
    """Where the manifest for this certificate tree lives."""
    return certs_root / MANIFEST_NAME


def entries(certs_root: Path) -> list[dict]:
    """One row per stored trace, as the certificates describe it."""
    rows = []
    for path in sorted(certs_root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8")).get("payload", {})
        except (json.JSONDecodeError, OSError):
            continue
        proof = payload.get("proof")
        if not proof:
            continue
        base = path.parent
        stored = base / proof["file"]
        rows.append({
            "certificate": path.relative_to(certs_root).as_posix(),
            "file": Path(proof["file"]).as_posix(),
            "text_sha256": proof["sha256"],
            "file_sha256": proof.get("file_sha256"),
            "steps": int(proof["steps"]),
            "encoding": proof.get("encoding", "ascii"),
            "stored_bytes": int(proof.get("stored_bytes", 0)),
            "exists": stored.exists(),
            "on_disk_sha256": hashlib.sha256(stored.read_bytes()).hexdigest()
            if stored.exists() else None,
        })
    return rows


def read_manifest(path: Path) -> dict[str, dict]:
    """Parse ``MANIFEST.txt``; a missing file reads as empty."""
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != len(COLUMNS):
            raise ValueError(f"{path}:{number}: expected {len(COLUMNS)} columns, got {len(fields)}")
        row = dict(zip(COLUMNS, fields))
        row["steps"] = int(row["steps"])
        row["stored_bytes"] = int(row["stored_bytes"])
        rows[row["file"]] = row
    return rows


def render(rows: list[dict], certs_root: Path | None = None) -> str:
    """The manifest text: header, then one line per trace, sorted by file name."""
    where = "certs/…"
    if certs_root is not None:
        try:
            where = certs_root.relative_to(ROOT).as_posix()
        except ValueError:
            where = certs_root.as_posix()
    head = [
        f"# Stored DRAT traces of {where}, pinned on purpose.",
        "# text_sha256 is the sha256 of the canonical proof text (what the certificate",
        "# records, and what survives re-encoding or re-compression); file_sha256 is the",
        "# sha256 of the bytes committed here.  Regenerate with:",
        "#",
        "#     python scripts/proof_manifest.py --write",
        "#",
        "# and only after deciding, deliberately, that the traces should change: the",
        "# point of this file is that such a change shows up in review.",
        "#",
        "# " + "  ".join(COLUMNS),
    ]
    body = [
        f"{row['text_sha256']}  {row['file_sha256']}  {row['steps']}  "
        f"{row['encoding']}  {row['stored_bytes']}  {row['file']}"
        for row in sorted(rows, key=lambda r: r["file"])
    ]
    return "\n".join(head + body) + "\n"


def check(certs_root: Path) -> list[str]:
    """Every disagreement between the manifest, the certificates and the disk."""
    problems: list[str] = []
    rows = entries(certs_root)
    if not rows:
        return [f"no certificate under {certs_root} records a DRAT trace"]
    pinned = read_manifest(manifest_path(certs_root))
    if not pinned:
        return [f"{manifest_path(certs_root)} is missing or empty: nothing is pinned"]

    for row in rows:
        found = pinned.get(row["file"])
        if found is None:
            problems.append(f"{row['file']}: stored and recorded by {row['certificate']}, "
                            f"but absent from the manifest")
            continue
        if found["text_sha256"] != row["text_sha256"]:
            problems.append(f"{row['file']}: the certificate's text sha256 is "
                            f"{row['text_sha256'][:16]}…, the manifest pins "
                            f"{found['text_sha256'][:16]}…")
        if row["file_sha256"] is not None and found["file_sha256"] != row["file_sha256"]:
            problems.append(f"{row['file']}: the certificate's file sha256 is "
                            f"{row['file_sha256'][:16]}…, the manifest pins "
                            f"{found['file_sha256'][:16]}…")
        if found["steps"] != row["steps"]:
            problems.append(f"{row['file']}: {row['steps']} steps recorded, "
                            f"{found['steps']} pinned")
        if found["stored_bytes"] != row["stored_bytes"]:
            problems.append(f"{row['file']}: {row['stored_bytes']} bytes recorded, "
                            f"{found['stored_bytes']} pinned")
        if not row["exists"]:
            problems.append(f"{row['file']}: pinned and recorded but not on disk")
        elif row["on_disk_sha256"] != found["file_sha256"]:
            problems.append(f"{row['file']}: the bytes on disk hash to "
                            f"{row['on_disk_sha256'][:16]}…, the manifest pins "
                            f"{found['file_sha256'][:16]}… (the trace changed, or the "
                            f"certificate was regenerated, without updating the manifest)")

    seen = {row["file"] for row in rows}
    for name in sorted(set(pinned) - seen):
        problems.append(f"{name}: pinned but no certificate records it")
    return problems


def write(certs_root: Path) -> int:
    """Rewrite the manifest from the certificates, refusing unpinnable rows."""
    rows = entries(certs_root)
    if not rows:
        print(f"no certificate under {certs_root} records a DRAT trace", file=sys.stderr)
        return 2
    for row in rows:
        if not row["exists"]:
            print(f"{row['file']}: recorded by {row['certificate']} but not on disk",
                  file=sys.stderr)
            return 2
        if row["file_sha256"] is None:
            print(f"{row['file']}: the certificate records no file_sha256, so the stored "
                  f"bytes cannot be pinned", file=sys.stderr)
            return 2
        if row["file_sha256"] != row["on_disk_sha256"]:
            print(f"{row['file']}: the bytes on disk are not the ones the certificate "
                  f"records — re-verify before pinning", file=sys.stderr)
            return 2
    path = manifest_path(certs_root)
    path.write_text(render(rows, certs_root), encoding="utf-8")
    print(f"{path} written: {len(rows)} traces pinned")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--certs", default=None,
                        help="the directory the manifest lives in "
                             "(default: certs/circulant_multicolour)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="report drift and exit 1 (default)")
    group.add_argument("--write", action="store_true", help="rewrite the manifest")
    args = parser.parse_args(argv)

    certs_root = Path(args.certs) if args.certs else Path("certs") / "circulant_multicolour"
    if not certs_root.is_absolute():
        certs_root = ROOT / certs_root
    if args.write:
        return write(certs_root)
    problems = check(certs_root)
    if problems:
        print(f"{len(problems)} problem(s) with the proof store:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    pinned = read_manifest(manifest_path(certs_root))
    total = sum(row["stored_bytes"] for row in pinned.values())
    print(f"proof store pinned: {len(pinned)} traces, {total / 1e6:.2f} MB, digests match "
          f"the certificates and the bytes on disk")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
