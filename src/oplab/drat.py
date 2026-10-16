"""DRAT proof checking: the trusted base behind every proved ``unsat``.

An ``unsat`` verdict is normally a claim about a program.  A *proof* turns it
into a claim about a file, and this module is the file's judge: it implements the
standard DRAT (deletion resolution asymmetric tautology) rules

* **RUP** — a clause ``C`` is accepted if assuming ``¬C`` and closing under unit
  propagation derives a conflict;
* **RAT** — a clause ``C`` with pivot ``C[0]`` is accepted if, for every clause
  ``D`` in the current formula containing ``¬C[0]``, the resolvent
  ``(C \\ {C[0]}) ∪ (D \\ {¬C[0]})`` is RUP (tautological resolvents are skipped);
* **deletion** — a ``d``-prefixed line removes one copy of that clause from the
  formula, weakening it for everything that follows;

and accepts a trace as a refutation when it derives the empty clause.  A trace
whose additions all pass RUP is also a valid DRAT trace, so the emitted proofs of
:mod:`oplab.multicolour` are checked by the same code path as any other.

Why this is worth 400 lines: the repository's ``unsat`` rows used to rest on
"CaDiCaL says so".  They now rest on this checker, which can be read in one
sitting, and on a trace that is stored beside the certificate — and on a *second,
unrelated* checker: ``scripts/drat_trim_check.py`` rebuilds each CNF from its
certificate and has ``drat-trim`` verify the stored trace, in CI (the
``drat-trim`` job) and on demand, so a bug here cannot keep a bad proof looking
good in every later run.  This checker is not trusted on faith either: the test
suite feeds it proofs whose truth is established independently (``R(3,3) = 6``,
proved by exhaustion in Lean, and the exhaustive ``2^21`` circulant sweeps),
proofs that have been tampered with, which it must reject, and a second,
deliberately naive implementation of the same two rules, which must agree with it
clause for clause.

Propagation is *two-watched-literal*: each clause of two or more distinct
literals watches two of them, and a clause is only visited when one of its
watches becomes false — the difference between replaying ``K45`` in 115 s and in
16 s.  The watch positions are state that survives between calls, which
is sound here because every call undoes its own assignments: at the start of a
call nothing is assigned, so every watch still points at a literal that is not
false, and the invariant the propagation relies on holds again.  One detail of
that bookkeeping is easy to get wrong and was: a conflict ends a call in the
middle of a watch list, and the entries that call never looked at are still
watching the falsified literal for the *next* call, so they have to be carried
over rather than dropped.  Dropping them loses propagations and makes the checker
reject valid traces — the stored ``K18`` and ``K30`` traces are what caught it.
``RAT`` still reads the occurrence lists (it has to look at every clause
containing the negated pivot), and those are maintained alongside.

Nothing here decides anything by itself: :func:`check_proof` never calls a
solver, and :func:`oplab.verify` uses it only on traces that a certificate
recorded, hashed and pinned.
"""

from __future__ import annotations

import gzip
import hashlib
import lzma
import time
from pathlib import Path

__all__ = [
    "parse_dimacs",
    "format_dimacs",
    "read_proof",
    "write_proof",
    "normalise",
    "proof_digest",
    "check_proof",
    "is_binary",
    "open_proof",
    "encode_binary",
    "decode_binary",
]


# --------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------
def parse_dimacs(path) -> tuple[int, list[list[int]]]:
    """Read a DIMACS CNF file into ``(num_vars, clauses)``.

    Comments (``c``) and the problem line (``p cnf``) are skipped; every other
    line is a clause terminated by ``0``, and a clause may be split over several
    lines (the DIMACS format allows it).
    """
    num_vars = 0
    clauses: list[list[int]] = []
    pending: list[int] = []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        line = line.strip()
        if not line or line[0] == "c":
            continue
        if line[0] == "p":
            header = line.split()
            num_vars = int(header[2])
            continue
        for token in line.split():
            lit = int(token)
            if lit == 0:
                clauses.append(pending)
                pending = []
            else:
                pending.append(lit)
    if pending:
        raise ValueError("the last clause is not terminated by 0")
    if not num_vars:
        num_vars = max((abs(l) for clause in clauses for l in clause), default=0)
    return num_vars, clauses


# --------------------------------------------------------------------------
# container: text or binary DRAT, optionally compressed
# --------------------------------------------------------------------------
# A stored trace is one of four things, and the name says which:
#
#   name.drat        name.drat.gz        name.drat.xz        ASCII DRAT text
#   name.bdrat       name.bdrat.gz       name.bdrat.xz       binary DRAT
#
# Binary DRAT is the encoding drat-trim reads in its `-i` mode: each clause
# starts with a byte, 97 (`a`) for an addition or 100 (`d`) for a deletion,
# followed by its literals and a zero byte, where a literal is written as
# ``2 * |lit| + (lit < 0)`` in base 128, least significant group first, with the
# high bit set on every group but the last.  It is what the traces are stored as:
# the same proof as text, about a third of the size before compression and
# smaller after it, and it is *readable by the external checker* rather than
# being a format only this module understands.
#
# The digest never depends on the container.  It is the sha256 of the canonical
# **text** (`proof_digest`), so re-compressing a trace, or moving it between text
# and binary, keeps every recorded digest meaningful and comparable — the
# certificate still pins the proof, not its encoding.
COMPRESSIONS = {".gz": gzip.open, ".xz": lzma.open}
ADD_PREFIX_BYTE = 97   # b"a"
DEL_PREFIX_BYTE = 100  # b"d"


def is_binary(path) -> bool:
    """Is this proof stored in binary DRAT?  (The name carries the format.)"""
    return ".bdrat" in Path(path).name


def open_proof(path, mode="rb"):
    """Open a proof for binary reading or writing, undoing the compression.

    Always binary: a proof's bytes are what gets stored and hashed, and both the
    text and the binary encoding are written as bytes so that no newline
    translation can get between us and a reproducible file.
    """
    if "b" not in mode:
        raise ValueError("open_proof is binary-only; use mode 'rb' or 'wb'")
    path = Path(path)
    opener = COMPRESSIONS.get(path.suffix, open)
    return opener(path, mode)


def encode_binary(lines) -> bytes:
    """Encode DRAT lines as binary DRAT, byte for byte as drat-trim writes it."""
    out = bytearray()
    for line in lines:
        kind, literals = _parse_step(line)
        out.append(DEL_PREFIX_BYTE if kind == "d" else ADD_PREFIX_BYTE)
        for lit in literals:
            value = (abs(lit) << 1) | (1 if lit < 0 else 0)
            while True:
                if value <= 127:
                    out.append(value)
                    break
                out.append(128 + (value & 127))
                value >>= 7
        out.append(0)
    return bytes(out)


def decode_binary(raw: bytes) -> list[str]:
    """Decode binary DRAT into the canonical text lines of the same proof."""
    lines: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        prefix = raw[i]
        i += 1
        if prefix not in (ADD_PREFIX_BYTE, DEL_PREFIX_BYTE):
            raise ValueError(f"byte {prefix} at {i - 1} is not a clause prefix (a or d)")
        literals: list[str] = []
        while True:
            value, shift = 0, 0
            while True:
                if i >= n:
                    raise ValueError("the proof ends inside a literal")
                byte = raw[i]
                i += 1
                value |= (byte & 127) << shift
                shift += 7
                if byte <= 127:
                    break
            if value == 0:
                break
            literals.append(str(-(value >> 1) if value & 1 else value >> 1))
        body = " ".join(literals)
        lines.append(("d " if prefix == DEL_PREFIX_BYTE else "") + (body + " 0" if body else "0"))
    return lines


def read_proof(path) -> list[str]:
    """Read a DRAT proof as a list of lines, whatever its container is.

    ``.gz``/``.xz`` are decompressed, ``.bdrat`` names are decoded from binary
    DRAT, and comment lines and blank lines are dropped: they carry no
    information, and ``drat-trim`` ignores them as well.
    """
    path = Path(path)
    with open_proof(path, "rb") as handle:
        raw = handle.read()
    if is_binary(path):
        return decode_binary(raw)
    return [line for line in (text.strip() for text in raw.decode("ascii").splitlines())
            if line and line[0] != "c"]


def normalise(lines) -> str:
    """The canonical text of a proof: one newline-terminated line per step."""
    return "".join(line + "\n" for line in lines)


def proof_digest(lines) -> str:
    """sha256 of the canonical proof text (independent of the container)."""
    return hashlib.sha256(normalise(lines).encode("ascii")).hexdigest()


def write_proof(path, lines) -> dict:
    """Write a proof, compressing and encoding it according to the name.

    Returns the metadata a certificate records: the canonical digest, the size of
    the uncompressed text, the step counts, and what was actually stored.
    """
    path = Path(path)
    text = normalise(lines)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    binary = is_binary(path)
    payload = encode_binary(lines) if binary else text.encode("ascii")
    with open_proof(path, "wb") as handle:
        handle.write(payload)
    additions = sum(1 for line in lines if line[0] != "d")
    stored = path.read_bytes()
    return {
        "file": path.as_posix(),
        # the semantic digest: sha256 of the canonical text, so it does not change
        # when the trace is re-encoded or re-compressed
        "sha256": proof_digest(lines),
        # and the bytes actually committed, hashed directly: the text digest says
        # *which* proof this is, this one says the file on disk is the file meant
        "file_sha256": hashlib.sha256(stored).hexdigest(),
        "bytes": len(text),
        "steps": len(lines),
        "added": additions,
        "deleted": len(lines) - additions,
        "encoding": "binary" if binary else "ascii",
        "payload_bytes": len(payload),
        "stored_bytes": len(stored),
    }


def format_dimacs(num_vars: int, clauses, comment: str = "") -> str:
    """Render ``(num_vars, clauses)`` as DIMACS text (the proof's other half)."""
    head = f"c {comment}\n" if comment else ""
    body = "".join(" ".join(map(str, clause)) + " 0\n" for clause in clauses)
    return f"{head}p cnf {num_vars} {len(clauses)}\n{body}"


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------
def _parse_step(line: str) -> tuple[str, tuple[int, ...]]:
    kind = "d" if line[0] == "d" else "a"
    body = line[1:].split() if kind == "d" else line.split()
    literals = tuple(int(token) for token in body if token != "0")
    return kind, literals


def check_proof(num_vars: int, clauses, proof_lines, *, max_steps: int | None = None) -> dict:
    """Check a DRAT trace against a CNF, with no solver involved.

    ``clauses`` is any iterable of integer sequences and ``proof_lines`` the DRAT
    text (as produced by :func:`read_proof`, or by ``pysat``'s ``get_proof``).
    The result is a dict with ``ok``, the step counts, the position of the empty
    clause, and — when the trace fails — the ``reason`` and the offending step.

    The state is the formula, its occurrence lists, its two-literal watches, the
    unit clauses and the active set; every check reads those and nothing else.
    """
    started = time.time()
    formula: list[tuple[int, ...]] = [tuple(int(l) for l in clause) for clause in clauses]
    active = [True] * len(formula)
    #: literal -> indices of clauses containing it (the RAT rule needs all of them)
    occ: dict[int, list[int]] = {}
    #: literal -> indices of clauses *watching* it (the propagation needs only these)
    watches: dict[int, list[int]] = {}
    #: per clause, the positions of its two watched literals
    watch_pos: list[tuple[int, int]] = []
    #: per clause, the literal it effectively asserts when it is unit-like
    unit_of: list[int | None] = []
    index: dict[tuple[int, ...], list[int]] = {}
    units: dict[int, int] = {}

    def attach(ci: int) -> None:
        """Index one clause: occurrences, content, and its two watches."""
        clause = formula[ci]
        for lit in clause:
            occ.setdefault(lit, []).append(ci)
        index.setdefault(tuple(sorted(clause)), []).append(ci)
        if len(set(clause)) <= 1:
            # unit, or (never emitted) several copies of one literal: it asserts
            # that literal and needs no watch — propagation seeds it every call
            unit_of.append(clause[0] if clause else None)
            if clause:
                units[clause[0]] = units.get(clause[0], 0) + 1
            watch_pos.append((-1, -1))
            return
        unit_of.append(None)
        watch_pos.append((0, 1))
        watches.setdefault(clause[0], []).append(ci)
        watches.setdefault(clause[1], []).append(ci)

    for ci in range(len(formula)):
        attach(ci)

    value = [0] * (num_vars + 1)
    trail: list[int] = []

    def propagate(assumed) -> int | None:
        """Close ``assumed`` under unit propagation; return a conflicting clause.

        ``assumed`` are literals taken to be *true*; the globally unit clauses are
        seeded first.  ``None`` means no conflict was reachable, which is what RUP
        needs in order to reject a clause.  Every assignment is undone before
        returning, which is what lets the watch positions persist across calls.
        """
        def set_true(lit: int) -> bool:
            var = lit if lit > 0 else -lit
            want = 1 if lit > 0 else -1
            current = value[var]
            if current:
                return current == want
            value[var] = want
            trail.append(lit)
            return True

        conflict: int | None = None
        for lit in assumed:
            if not set_true(lit):
                conflict = -1  # the assumptions themselves conflict: trivially RUP
                break
        if conflict is None:
            for lit in units:
                if not set_true(lit):
                    conflict = -1
                    break

        cursor = 0
        while conflict is None and cursor < len(trail):
            falsified = -trail[cursor]
            cursor += 1
            bucket = watches.get(falsified)
            if not bucket:
                continue
            keep: list[int] = []
            done = 0
            for ci in bucket:
                done += 1
                if not active[ci]:
                    continue
                clause = formula[ci]
                first, second = watch_pos[ci]
                if clause[first] == falsified:
                    pos, other = first, second
                elif clause[second] == falsified:
                    pos, other = second, first
                else:
                    continue  # stale entry: this clause moved its watch already
                other_lit = clause[other]
                if value[other_lit if other_lit > 0 else -other_lit] == (1 if other_lit > 0 else -1):
                    keep.append(ci)  # satisfied: the watch can stay where it is
                    continue
                replacement = -1
                for i, lit in enumerate(clause):
                    if i == pos or i == other:
                        continue
                    if value[lit if lit > 0 else -lit] != -(1 if lit > 0 else -1):
                        replacement = i
                        break
                if replacement >= 0:
                    watch_pos[ci] = ((replacement, other) if pos == first
                                     else (other, replacement))
                    watches.setdefault(clause[replacement], []).append(ci)
                    continue
                # nothing else to watch: the clause is unit on `other`, or false
                keep.append(ci)
                if not set_true(other_lit):
                    conflict = ci
                    break
            if conflict is not None and done < len(bucket):
                # a conflict ends the propagation here, so the clauses of this
                # bucket that were not looked at yet are still watching the
                # falsified literal: they must survive into the next call
                keep.extend(bucket[done:])
            watches[falsified] = keep

        for lit in trail:
            value[lit if lit > 0 else -lit] = 0
        trail.clear()
        return conflict

    def rup(clause: tuple[int, ...]) -> int | None:
        return propagate(tuple(-l for l in clause))

    def rat(clause: tuple[int, ...]) -> bool:
        """The RAT rule on the first literal of ``clause``."""
        pivot, rest = clause[0], clause[1:]
        for di in list(occ.get(-pivot, ())):
            if not active[di]:
                continue
            resolved = list(rest) + [l for l in formula[di] if l != -pivot]
            if any(-l in resolved for l in resolved):
                continue  # tautological resolvent: nothing to check
            if propagate(tuple(-l for l in resolved)) is None:
                return False
        return True

    added = deleted = missing_deletions = 0
    for step, line in enumerate(proof_lines):
        if max_steps is not None and step >= max_steps:
            return {"ok": False, "reason": f"step limit {max_steps} reached before the empty clause",
                    "steps": step, "seconds": time.time() - started}
        kind, literals = _parse_step(line if isinstance(line, str) else line.decode("ascii"))
        if kind == "d":
            # clauses are matched by content: a solver may print the literals in
            # any order, so the lookup key is the sorted clause, not the line
            bucket = index.get(tuple(sorted(literals)))
            target = None
            while bucket:
                candidate = bucket.pop()
                if active[candidate]:
                    target = candidate
                    break
            if target is None:
                missing_deletions += 1
                continue
            active[target] = False
            if unit_of[target] is not None:
                units[unit_of[target]] -= 1
                if units[unit_of[target]] <= 0:
                    del units[unit_of[target]]
            deleted += 1
            continue

        if any(lit == 0 or abs(lit) > num_vars for lit in literals):
            return {"ok": False, "reason": f"step {step + 1}: literal outside 1..{num_vars}",
                    "steps": step, "seconds": time.time() - started}
        # the empty clause has no pivot, so RAT cannot apply to it: it is rejected
        # unless RUP already refutes the formula.  (Getting this wrong accepts every
        # proof that pastes an empty clause at the top, which is what the tampering
        # test in tests/test_drat.py watches for.)
        conflict = rup(literals)
        if conflict is None and (not literals or not rat(literals)):
            return {
                "ok": False,
                "reason": (
                    f"step {step + 1}: clause {' '.join(map(str, literals))} 0 is neither "
                    "RUP nor RAT against the formula built so far"
                ),
                "steps": step,
                "seconds": time.time() - started,
            }
        formula.append(literals)
        active.append(True)
        attach(len(formula) - 1)
        added += 1
        if not literals:
            return {
                "ok": True,
                "steps": step + 1,
                "added": added,
                "deleted": deleted,
                "missing_deletions": missing_deletions,
                "num_vars": num_vars,
                "num_clauses": len(clauses),
                "empty_clause_at": step + 1,
                "seconds": time.time() - started,
            }

    return {
        "ok": False,
        "reason": "the trace ends without deriving the empty clause",
        "steps": len(proof_lines),
        "added": added,
        "deleted": deleted,
        "missing_deletions": missing_deletions,
        "seconds": time.time() - started,
    }
