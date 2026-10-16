"""Tests for the Cayley (translation-invariant over arbitrary groups) layer.

Three things are checked here and nothing is assumed: that every table the module
builds really is a group, that over the *cyclic* group the encoding is exactly the
circulant one the repository already trusts, and that the known Ramsey facts hold
over *every* group the module can build — which is what makes a witness found in
one of them worth anything.  The certificate kind has its own acceptance and
forgery tests, and the obstruction is checked to fire for all groups, not just the
cyclic one.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from oplab import cayley as CY
from oplab import multicolour as MC
from oplab.verify import make_certificate, payload_hash, verify_certificate

SOLVER = bool(MC.available_solvers())


def _sizes_cases():
    return [
        ("abelian", [6]), ("abelian", [8]), ("abelian", [4, 2]), ("abelian", [2, 2, 2]),
        ("dihedral", [3]), ("dihedral", [4]), ("dihedral", [8]),
        ("dicyclic", [2]), ("dicyclic", [4]), ("semidihedral", [8]), ("semidihedral", [16]),
        ("product", [{"family": "abelian", "params": [4]},
                     {"family": "dihedral", "params": [3]}]),
    ]


def test_every_generated_table_satisfies_the_group_axioms():
    """The hand-derived families are only as good as this check.

    Dihedral, dicyclic and semidihedral tables are derived from their relations;
    identity, inverses and associativity over every triple are re-derived here, so a
    wrong multiplication rule fails loudly instead of quietly searching a non-group.
    """
    for family, params in _sizes_cases():
        table, inverse = CY.group_from_description({"family": family, "params": params})
        result = CY.verify_group(table, inverse)
        assert result["ok"], f"{family}{params}: {result.get('reason')}"


def test_abelian_groups_are_classified_correctly():
    """The classification theorem, on the sizes the search actually uses."""
    assert CY.abelian_groups(97) == [[97]]
    assert CY.abelian_groups(128) and len(CY.abelian_groups(128)) == 15  # partitions of 7
    assert len(CY.abelian_groups(96)) == 7                               # 2^5 * 3
    for signature in CY.abelian_groups(96):
        product_of = 1
        for factor in signature:
            product_of *= factor
        assert product_of == 96


def test_the_inversion_classes_pair_an_element_with_its_inverse():
    for family, params in _sizes_cases():
        table, inverse = CY.group_from_description({"family": family, "params": params})
        classes, class_of = CY.inversion_classes(table, inverse)
        assert len(classes) == len(set(classes))
        for d in range(1, len(table)):
            assert class_of[d] == min(d, inverse[d])
            assert class_of[inverse[d]] == class_of[d]
        assert set(classes) == set(class_of.values())


def test_over_the_cyclic_group_the_encoding_is_the_circulant_one():
    """The new family must contain the old one exactly, not merely resemble it."""
    for n, s in ((17, 4), (18, 4), (29, 3), (30, 3), (51, 3)):
        instance = CY.CayleyInstance({"family": "abelian", "params": [n]}, (s,))
        mine = {tuple(sorted(instance.classes.index(c) for c in group))
                for group in instance.groups[s]}
        theirs = {tuple(sorted(instance.classes.index(MC.difference_class(d, n)) for d in group))
                  for group in MC.clique_class_groups(n, s)}
        assert mine == theirs, f"K{n} s={s}: the class sets differ"
        assert instance.total_vars() == MC.CirculantInstance(n, (s,)).total_vars()


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_known_ramsey_facts_hold_over_every_group_of_the_order():
    """R(3,3) = 6 and R(4,4) = 18 are decided: no colouring exists, on any group.

    Over K5 and K17 a witness must appear (and be re-counted clean); over K6 and K18
    *every* group the module builds must come back UNSAT, whatever its structure.
    """
    cases = (
        (5, (3, 3), {"sat"}),          # R(3,3) = 6, so K5 is clean
        (6, (3, 3), {"obstructed"}),   # and K6 is decided by arithmetic, not by a solver
        (17, (4, 4), {"sat"}),         # R(4,4) = 18
        (18, (4, 4), {"unsat"}),       # no 2-colouring of K18 is clean, on any group
        (30, (3, 3, 4), {"unsat"}),    # R(3,3,4) = 30: not an all-triangle instance,
                                       # so this one is a verdict on every group
    )
    for n, sizes, allowed in cases:
        groups = CY.groups_of_order(n)
        assert groups
        for description in groups:
            result = CY.cayley_solve(description, sizes, seconds=120.0)
            assert result["status"] in allowed, (description["name"], result["status"])
            if result["status"] == "sat":
                assert result["verified"]["valid"], description["name"]
                assert result["verified"]["establishes"] == f"R{sizes} > {n}"


def test_the_obstruction_is_arithmetic_and_fires_for_every_group():
    """``3 | n`` and an all-triangle instance: group theory decides it, not a solver.

    Cauchy's theorem gives an element of order 3 in *any* group of order ``n``, so
    the ``n/3`` translates of ``{e, g, g²}`` are monochromatic in the colour of one
    single class.  The cyclic case was already in the repository; this one is shown
    here for every group the module can build, and with no solver in the loop.
    """
    from oplab import multicolour as MC_MOD

    for n in (6, 18, 30, 51, 96, 162):
        for description in CY.groups_of_order(n):
            obstruction = CY.cayley_obstruction(description, (3, 3, 3, 3))
            if n % 3:
                assert obstruction is None
                continue
            assert obstruction is not None, description["name"]
            assert obstruction["triangles"] == n // 3
        # the cyclic case agrees with the repository's own obstruction
        if n % 3 == 0:
            assert MC_MOD.circulant_obstruction(n, (3, 3, 3, 3)) is not None
    declared = CY.cayley_obstruction({"family": "dihedral", "params": [3]}, (3, 3, 3, 3))
    assert declared is not None and declared["class_order"] == 3
    # a non-triangle instance is not obstructed
    assert CY.cayley_obstruction({"family": "dihedral", "params": [3]}, (3, 3, 4)) is None


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_an_obstructed_instance_is_decided_without_a_solver():
    # D15 has order 30, so the obstruction fires on it as well as on the cyclic group
    result = CY.cayley_solve({"family": "dihedral", "params": [15]}, (3, 3, 3, 3))
    assert result["status"] == "obstructed"
    assert result["seconds"] == 0.0
    assert result["obstruction"]["triangles"] == 10


def _witness_certificate(n=17, sizes=(4, 4)):
    description = {"family": "abelian", "params": [n], "name": "cyclic"}
    result = CY.cayley_solve(description, sizes, seconds=120.0)
    assert result["status"] == "sat", result
    payload = {
        "n": n,
        "sizes": list(sizes),
        "status": "sat",
        "group": description,
        "classes": result["classes"],
        "num_vars": result["num_vars"],
        "num_clauses": result["num_clauses"],
        # a certificate is JSON: the keys are strings on disk, so they are strings here
        "class_colors": {str(k): int(v) for k, v in result["class_colors"].items()},
        "coloring": result["coloring"],
        # the group as data: the table, its inverse list and the clique groups
        **CY.CayleyInstance(description, sizes).certificate_payload(),
    }
    return make_certificate(
        "cayley_multicolour",
        f"K{n} {list(sizes)} over the cyclic group",
        payload,
        {"n": n, "sizes": list(sizes), "status": "sat",
         "monochromatic_cliques": result["verified"]["monochromatic_cliques"]},
        {"generator": "oplab cayley (test)", "created": "2026-10-16"},
    )


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_a_cayley_witness_verifies_and_leaves_nothing_untrusted():
    cert = _witness_certificate()
    result = verify_certificate(cert)
    assert result["ok"], result.get("reason")
    assert "translation-invariant witness" in result["establishes"]
    assert result["checks"]["num_vars"] == cert["payload"]["num_vars"]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_the_cayley_verifier_rejects_a_forged_assignment():
    """Flip one class colour and the exact counter has to notice."""
    cert = _witness_certificate()
    first = sorted(int(k) for k in cert["payload"]["class_colors"])[0]
    forged = copy.deepcopy(cert)
    forged["payload"]["class_colors"][str(first)] = (
        1 - int(forged["payload"]["class_colors"][str(first)])
    )
    forged["payload"].pop("coloring")
    forged["payload_sha256"] = payload_hash(forged["payload"])
    result = verify_certificate(forged)
    assert not result["ok"], result
    assert "not clean" in result["reason"] or "disagrees" in result["reason"]


def test_verify_group_rejects_a_table_that_is_not_a_group():
    """The axiom check is the reason the hand-derived families can be trusted."""
    table, inverse = CY.group_from_description({"family": "dihedral", "params": [4]})
    assert CY.verify_group(table, inverse)["ok"]
    broken = [row[:] for row in table]
    broken[1][2] = broken[0][0]  # r * r^2 = e: not associative any more
    broken[2][1] = broken[0][0]
    result = CY.verify_group(broken, inverse)
    assert not result["ok"], result
    assert "associative" in result["reason"] or "inverse" in result["reason"]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_the_cayley_verifier_refuses_a_group_of_the_wrong_order():
    """A description rebuilds the group, so a payload about K17 in a group of order 12
    must not verify: the class count and the encoding size give it away."""
    cert = _witness_certificate()
    broken = copy.deepcopy(cert)
    broken["payload"]["group"] = {"family": "abelian", "params": [4, 3], "name": "Z4xZ3"}
    broken["payload_sha256"] = payload_hash(broken["payload"])
    result = verify_certificate(broken)
    assert not result["ok"], result
    assert "variables" in result["reason"] or "classes" in result["reason"]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_the_cayley_verifier_will_not_carry_an_unsat_verdict():
    """A verdict over one group needs a DRAT trace; a witness row has none."""
    cert = _witness_certificate()
    smuggled = copy.deepcopy(cert)
    smuggled["payload"]["status"] = "unsat"
    smuggled["payload_sha256"] = payload_hash(smuggled["payload"])
    result = verify_certificate(smuggled)
    assert not result["ok"], result
    assert "DRAT" in result["reason"]


def _group_of(n: int, name: str) -> dict:
    return next(g for g in CY.groups_of_order(n) if g["name"] == name)


def _unsat_certificate(tmp_path: Path, n: int = 18, sizes=(4, 4), group: str = "D9"):
    """Decide one group and store the pair the way ``oplab cayley`` does.

    Three steps, in this order, and the order is the point: the solver writes its
    trace, :func:`oplab.cayley.replay_proof` re-checks it against this group's
    encoding with no solver in the loop, and only then is the certificate written.
    The verifier tests below are handed a row built exactly as the repository
    builds one.
    """
    description = _group_of(n, group)
    sizes = tuple(sizes)
    stem = f"k{n}_{'x'.join(map(str, sizes))}_{group}"
    proof_path = tmp_path / f"{stem}.bdrat.xz"
    result = CY.cayley_solve(description, sizes, seconds=120.0, proof_path=proof_path)
    assert result["status"] == "unsat", result
    recorded = CY.replay_proof(description, sizes, proof_path, base_dir=tmp_path)
    assert recorded["ok"], recorded
    instance = CY.CayleyInstance(description, sizes)
    payload = {
        "n": n,
        "sizes": list(sizes),
        "status": "unsat",
        "group": description,
        "classes": len(instance.classes),
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
        "proof": {key: value for key, value in recorded.items() if key != "ok"},
        **instance.certificate_payload(),
    }
    cert = make_certificate(
        "cayley_multicolour",
        f"K{n} {list(sizes)} over {group}: unsat",
        payload,
        {"n": n, "sizes": list(sizes), "status": "unsat"},
        {"generator": "oplab cayley (test)", "created": "2026-10-16"},
    )
    return cert, tmp_path


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_a_cayley_unsat_row_is_a_theorem_only_with_a_replayed_trace(tmp_path):
    """The trace is what turns the row into a statement about one group.

    With it, the verifier replays it against the encoding rebuilt from the group
    description and says which group the statement is about; without it, the row is
    refused — this kind stores no bare verdicts, so a certificate that carries one
    is not a weaker theorem, it is not a theorem at all.
    """
    cert, base = _unsat_certificate(tmp_path)
    result = verify_certificate(cert, base_dir=base)
    assert result["ok"], result.get("reason")
    assert "D9" in result["establishes"] and "replayed" in result["establishes"]
    assert result["checks"]["proof"]["replayed"] is True

    stripped = copy.deepcopy(cert)
    stripped["payload"].pop("proof")
    stripped["payload_sha256"] = payload_hash(stripped["payload"])
    result = verify_certificate(stripped, base_dir=base)
    assert not result["ok"], result
    assert "DRAT" in result["reason"]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_a_trace_is_bound_to_the_group_it_was_produced_for(tmp_path):
    """D9's refutation is not Z3xD3's: the replay says so, nothing else can.

    Both are groups of order 18, and after the payload's counts are made consistent
    with the second group every size check passes — only replaying the trace against
    the encoding the certificate *declares* separates the two rows.  A cyclic trace
    would do the same to a dihedral row, which is why the replay is not optional and
    why the two families cannot share a stored trace.
    """
    cert, base = _unsat_certificate(tmp_path)
    other = copy.deepcopy(cert)
    description = _group_of(18, "Z3xD3")
    other["payload"]["group"] = description
    instance = CY.CayleyInstance(description, (4, 4))
    other["payload"]["classes"] = len(instance.classes)
    other["payload"]["num_vars"] = instance.total_vars()
    other["payload"]["num_clauses"] = instance.clause_count()
    other["payload"].update(instance.certificate_payload())
    other["payload_sha256"] = payload_hash(other["payload"])
    result = verify_certificate(other, base_dir=base)
    assert not result["ok"], result
    assert result["checks"]["proof"]["ok"] is False
    # and the same refusal comes from the replay helper the writers call first
    direct = CY.replay_proof(description, (4, 4), base / cert["payload"]["proof"]["file"])
    assert not direct["ok"], direct


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_an_edited_cayley_trace_is_caught_by_its_digests(tmp_path):
    cert, base = _unsat_certificate(tmp_path)
    path = base / cert["payload"]["proof"]["file"]
    lines = MC.DRAT.read_proof(path)
    lines.insert(1, "0")  # an early, unjustified empty clause
    MC.DRAT.write_proof(path, lines)
    result = verify_certificate(cert, base_dir=base)
    assert not result["ok"], result
    assert "sha256" in result["reason"]


def test_the_cayley_verifier_refuses_an_unsat_claim_where_arithmetic_decides():
    """``3 | n`` on an all-triangle instance has to be recorded as ``obstructed``.

    The obstruction fires in every group of the order, so an ``unsat`` row here is a
    description of a solver run where an arithmetic fact was available; no trace was
    looked for (there is none in this certificate) because the status is wrong.
    """
    description = {"family": "dihedral", "params": [3], "name": "D3"}
    instance = CY.CayleyInstance(description, (3, 3))
    cert = make_certificate(
        "cayley_multicolour",
        "K6 (3,3) over D3: unsat",
        {
            "n": 6, "sizes": [3, 3], "status": "unsat", "group": description,
            "classes": len(instance.classes), "num_vars": instance.total_vars(),
            "num_clauses": instance.clause_count(),
            "proof": {"file": "nowhere.bdrat", "sha256": "0" * 64, "steps": 1},
            **instance.certificate_payload(),
        },
        {"n": 6, "sizes": [3, 3], "status": "unsat"},
        {"generator": "test", "created": "2026-10-16"},
    )
    result = verify_certificate(cert)
    assert not result["ok"], result
    assert "obstructed" in result["reason"]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_the_hunt_records_a_replayed_proof_and_the_reduced_cnf(tmp_path):
    """The script's `--proof-dir`/`--cnf-dir` path, exercised as a reader uses it.

    A trace that no one re-checks is not worth storing, so the script replays what
    the solver emitted before attaching it, names it after the group, and writes the
    certificate that cites it.  The reduced CNF is exported beside it for a
    full-strength solver, and its header has to be the encoding the certificate
    declares.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "cayley_hunt.py"
    cert_dir, cnf_dir = tmp_path / "cayley", tmp_path / "dimacs"
    result = subprocess.run(
        [sys.executable, str(script), "18:4,4", "--group", "D9", "--seconds", "60",
         "--workers", "1", "--cert-dir", str(cert_dir),
         "--proof-dir", str(cert_dir / "proofs"), "--cnf-dir", str(cnf_dir)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    stored = cert_dir / "k18_4x4_D9.json"
    assert stored.exists(), result.stdout
    cert = json.loads(stored.read_text(encoding="utf-8"))
    assert cert["payload"]["status"] == "unsat"
    assert cert["payload"]["proof"]["file"] == "proofs/k18_4x4_D9.bdrat.xz"
    assert (cert_dir / cert["payload"]["proof"]["file"]).exists()
    check = verify_certificate(cert, base_dir=cert_dir)
    assert check["ok"], check.get("reason")
    header = (cnf_dir / "k18_4x4_D9.cnf").read_text(encoding="ascii").splitlines()
    instance = CY.CayleyInstance(_group_of(18, "D9"), (4, 4))
    assert header[1] == f"p cnf {instance.total_vars()} {instance.clause_count()}", header[1]


@pytest.mark.skipif(not SOLVER, reason="no bundled SAT solver")
def test_the_hunt_script_finds_the_anchors_and_invents_nothing():
    """The script is the interface; it must reproduce the facts and stop at a witness."""
    script = Path(__file__).resolve().parents[1] / "scripts" / "cayley_hunt.py"
    result = subprocess.run(
        [sys.executable, str(script), "5:3,3", "6:3,3", "18:4,4", "--seconds", "60",
         "--workers", "4"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert any("K5 (3, 3): WITNESS over cyclic" in line for line in lines), result.stdout
    for blocked in ("K6 (3, 3)", "K18 (4, 4)"):
        assert any(blocked + ": no witness" in line for line in lines), result.stdout
    # every group of order 6 and 18 is searched, not just the cyclic one
    assert sum(1 for line in lines if "unsat" in line) >= 6, result.stdout


def test_the_repair_finds_a_known_witness_and_never_invents_one():
    """The local search is weaker than CDCL, and it must be honest about that.

    On K17 (clean, since R(4,4) = 18) it has to produce a witness that the ordinary
    verifier re-counts; on K18 — where *no* 2-colouring is clean, on any group — it
    may only report a spent budget with the violations it could not remove.  A near
    miss is never a witness here.
    """
    good = CY.repair({"family": "abelian", "params": [17]}, (4, 4), seconds=20.0, seed=3)
    assert good["status"] == "sat", good
    assert good["verified"]["valid"] and good["verified"]["establishes"] == "R(4, 4) > 17"

    bad = CY.repair({"family": "abelian", "params": [18]}, (4, 4), seconds=10.0, seed=3)
    assert bad["status"] == "unknown", bad
    assert bad["best_violations"] >= 1
    assert "coloring" not in bad


def test_every_child_is_told_the_budget_it_may_spend(monkeypatch, tmp_path):
    """The budget is part of the job, not only of the parent's kill timeout.

    The repair engine races its own clock — it is given slightly less than the
    parent's budget so that it returns its best attempt instead of being killed —
    and it read that budget from the job.  The job never carried one, so `--mode
    repair` raised `KeyError: 'seconds'` in every child and searched nothing at all;
    the stub here reports the job it was handed, because that is the interface.
    """
    import importlib
    import multiprocessing as mp

    (tmp_path / "echoing_engine.py").write_text(
        "def report(conn, job):\n"
        "    conn.send({'status': 'probe', 'budget': job.get('seconds'),\n"
        "               'n': job.get('n'), 'sizes': job.get('sizes')})\n", encoding="utf-8")
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    sys.path.insert(0, str(tmp_path))
    try:
        echoing = importlib.import_module("echoing_engine")
        hunt = importlib.import_module("cayley_hunt")
        monkeypatch.setattr(hunt, "_group_worker", echoing.report)
        job = {"group": _group_of(18, "D9"), "n": 18, "sizes": [4, 4],
               "mode": "repair", "seed": 0}
        rows = hunt._run_batch(mp.get_context("spawn"), [job], 7.0, "cadical195")
    finally:
        sys.path.remove(str(tmp_path))
        sys.path.remove(str(scripts))
    assert len(rows) == 1
    assert rows[0]["status"] == "probe"
    assert rows[0]["budget"] == 7.0
    assert rows[0]["n"] == 18 and rows[0]["sizes"] == [4, 4]


def _script_module(name: str):
    """A script under `scripts/` as a module, for the tests that call into it.

    They are scripts, not package members, so they are imported from their path —
    which is also how the parent hands a child the module to resolve the worker in.
    """
    import importlib

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module(name)


def _hunt_module():
    """The Cayley sweep driver, whose helpers the tests below call directly."""
    return _script_module("cayley_hunt")


def test_an_engine_that_refuses_the_instance_still_leaves_a_row_with_its_identity():
    """An error row has to say what was searched, or the sweep dies on it.

    The repair engine is a witness hunter and the CDCL one a decider; either can be
    handed something it cannot build and then reports `error` with the reason.  That
    row used to carry no `sizes` and no `n`, and the parent crashed on the first one
    it tried to record — losing the rows the batch had already decided.  The identity
    comes from the job, so it is there whatever the engine managed to say, and
    `_record_decision`, which reads it, can no longer be the thing that dies.
    """
    hunt = _hunt_module()

    class Sink:
        """What `_group_worker` writes to, in place of a pipe."""

        def __init__(self):
            self.rows = []

        def send(self, row):
            self.rows.append(row)

        def close(self):
            pass

    sink = Sink()
    job = {"group": _group_of(18, "D9"), "n": 18, "sizes": [4, 4],
           "mode": "cdcl", "solver": "no-such-engine-bundled-here"}
    hunt._group_worker(sink, job)
    assert len(sink.rows) == 1
    row = sink.rows[0]
    assert row["status"] == "error" and row["reason"], row
    assert row["n"] == 18 and row["sizes"] == [4, 4]
    assert row["group"] == job["group"] and row["name"] == "D9"
    # and the parent's recorder accepts that row: nothing to store, nothing raised
    assert hunt._record_decision(row, None, None, None) is None


def test_a_child_that_dies_without_a_word_costs_one_row_and_not_the_sweep(monkeypatch,
                                                                        tmp_path):
    """An engine that dies hard is a row, not the end of the run.

    This is not hypothetical: the bundled Kissat wheel segfaults on this platform,
    and the sweep was first seen to die with it — the child closed the pipe without
    sending a summary, `parent.poll` raised out of `_run_batch`, and every row the
    batch had already decided went with it.  A worker that dies that way has to
    leave a `no_verdict` row carrying its exit code *and* the instance it was asked
    about.  The dying child is a stub written to disk, because a parent cannot
    patch a function into a process it spawns.
    """
    import importlib
    import multiprocessing as mp

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    (tmp_path / "dying_engine.py").write_text(
        "import os\n\n\ndef die(conn, job):\n    os._exit(9)\n", encoding="utf-8")
    sys.path.insert(0, str(scripts))
    sys.path.insert(0, str(tmp_path))
    try:
        dying = importlib.import_module("dying_engine")
        hunt = importlib.import_module("cayley_hunt")
        monkeypatch.setattr(hunt, "_group_worker", dying.die)
        job = {"group": _group_of(18, "D9"), "sizes": [4, 4], "mode": "cdcl", "seed": 0}
        rows = hunt._run_batch(mp.get_context("spawn"), [job], 5.0, "cadical195")
    finally:
        sys.path.remove(str(tmp_path))
        sys.path.remove(str(scripts))
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "no_verdict", row
    assert row["exit_code"] == 9, row
    # and the row still says which instance that engine was asked about, because
    # an anonymous row is not evidence of anything
    assert row["name"] == "D9" and row["n"] == 18 and row["sizes"] == [4, 4]
    assert row["num_vars"] and row["num_clauses"]


def test_the_merge_supersedes_a_row_and_keeps_what_it_replaced(tmp_path):
    """A longer round is a visible diff, not a rewritten row.

    `runs/cayley_sweep.json` is quoted by RESULTS.md and by the README, so the earlier
    attempt has to survive the merge: the frontier takes the new row, `superseded`
    keeps the row it replaced, the counts are recomputed from the frontier, and a row
    about a group the sweep does not have is refused — that is a portfolio change, not
    a longer round.
    """
    merge = _script_module("sweep_merge")
    group = _group_of(18, "D9")
    sweep_path = tmp_path / "sweep.json"
    sweep_path.write_text(json.dumps({
        "what": "test", "produced_by": "test", "reading": "test",
        "totals": {}, "per_target": [], "snapshot": "2026-10-16",
        "rows": [{"name": "D9", "n": 18, "sizes": [4, 4], "group": group,
                  "status": "unknown", "seconds": 300.0, "classes": 9,
                  "num_vars": 26, "num_clauses": 186}],
    }), encoding="utf-8")
    decided = {"name": "D9", "n": 18, "sizes": [4, 4], "group": group,
               "status": "unsat", "seconds": 3605.0, "classes": 9,
               "num_vars": 26, "num_clauses": 186, "solver": "cadical195"}
    round_path = tmp_path / "round.json"
    round_path.write_text(json.dumps([decided]), encoding="utf-8")
    assert merge.main([str(sweep_path), str(round_path), "--write"]) == 0

    merged = json.loads(sweep_path.read_text(encoding="utf-8"))
    assert merged["rows"][0]["status"] == "unsat"
    assert merged["totals"] == {"unsat": 1}
    assert merged["per_target"] == [{"n": 18, "sizes": [4, 4],
                                     "groups": {"unsat": 1}, "group_count": 1}]
    # the 300 s attempt is still on the record, and the round names where it came from
    assert [row["seconds"] for row in merged["superseded"]] == [300.0]
    assert merged["rounds"][0]["file"] == "round.json"
    assert merged["rounds"][0]["decisions_changed"] == 1

    # a row about another group, and a repair row, are both refused (exit 2)
    (tmp_path / "stranger.json").write_text(
        json.dumps([dict(decided, name="D3", n=6)]), encoding="utf-8")
    assert merge.main([str(sweep_path), str(tmp_path / "stranger.json")]) == 2
    (tmp_path / "repair.json").write_text(
        json.dumps([dict(decided, status="unknown", repair_moves=7)]), encoding="utf-8")
    assert merge.main([str(sweep_path), str(tmp_path / "repair.json")]) == 2


def test_the_replay_bench_times_the_in_repo_checker_without_a_native_one(tmp_path):
    """The bench is the measurement, so it has to work with no external checker.

    `--skip-native` times `oplab.drat` on a stored trace and writes the rows: that is
    the half of the comparison this repository can always reproduce, and the half CI
    can run without drat-trim, so it is the half that has to be exercised here.
    """
    script = Path(__file__).resolve().parents[1] / "scripts" / "replay_bench.py"
    out = tmp_path / "bench.json"
    result = subprocess.run(
        [sys.executable, str(script), "--skip-native", "--only", "k18_4x4_D9",
         "--json", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    row, = payload["rows"]
    assert row["tag"] == "k18_4x4_D9" and row["steps"] == 122
    assert row["python"]["ok"] and row["python"]["seconds"] > 0
    assert row["python"]["steps_checker_read"] == 122
    assert row["python"]["num_clauses"] > 0


# --------------------------------------------------------------------------
# the complete portfolio: every group of one order, imported from GAP
# --------------------------------------------------------------------------
def _portfolio_path(n: int) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / f"smallgroups_{n}.json"


def test_a_permutation_description_closes_to_the_group_it_names():
    """The imported family is a construction, and its order is what is checked.

    A group exported from the SmallGroups library travels as permutation generators,
    and the table is rebuilt here by closing them under composition: the elements
    *are* permutations, so associativity is inherited and the one thing that can be
    wrong is the size.  A closure that is not the declared order is refused, which is
    what keeps a truncated, edited or mis-exported file from becoming a sweep over
    some other group — and the invariants of the rebuilt table are the same ones the
    dihedral family gives for the same group, which checks both constructions.

    """
    # S3 as it sits in S3: a transposition and a 3-cycle
    description = {"family": "permutation", "params": [6, [[1, 0, 2], [1, 2, 0]]],
                   "name": "S3"}
    table, inverse = CY.group_from_description(description)
    assert len(table) == 6
    result = CY.verify_group(table, inverse, description)
    assert result["ok"] and result["method"] == "permutation closure"
    signature = CY.portfolio_signature(table, inverse)
    assert signature == {"orders": {"1": 1, "2": 3, "3": 2},
                         "classes": {"1:1": 1, "2:3": 1, "3:2": 1},
                         "center": 1, "derived": 3, "exponent": 6, "abelian": False}
    dihedral = CY.group_from_description({"family": "dihedral", "params": [3]})
    assert CY.portfolio_signature(*dihedral) == signature

    # the same generators declared as a group of order 12, and a non-permutation
    # generator, are both refused
    with pytest.raises(ValueError, match="order 6, not 12"):
        CY.group_from_description({"family": "permutation", "params": [12,
                                   [[1, 0, 2], [1, 2, 0]]]})
    with pytest.raises(ValueError, match="not a permutation"):
        CY.group_from_description({"family": "permutation", "params": [6,
                                   [[0, 0, 2], [1, 2, 0]]]})
    with pytest.raises(ValueError, match="different numbers of points"):
        CY.group_from_description({"family": "permutation", "params": [6,
                                   [[1, 0, 2], [1, 2]]]})


def test_the_permutation_check_refuses_a_table_from_somewhere_else():
    """Passing the description re-derives the closure, so a foreign table is caught.

    The cubic axiom check accepts any group's table, which is exactly what a
    certificate must not be able to exploit: a row that *claims* to be about
    ``SmallGroup(96,1)`` has to carry that group's table.  Handing the description to
    :func:`oplab.cayley.verify_group` is what turns "this is a group" into "this is
    the group the description names".
    """
    description = {"family": "permutation", "params": [6, [[1, 0, 2], [1, 2, 0]]],
                   "name": "S3"}
    table, inverse = CY.group_from_description(description)
    other, other_inverse = CY.group_from_description({"family": "abelian", "params": [6]})
    assert CY.verify_group(table, inverse, description)["ok"] is True
    assert CY.verify_group(other, other_inverse, description)["ok"] is False
    assert CY.verify_group(table, other_inverse, description)["ok"] is False
    # the same table without a description is still a group: the cubic check is the
    # weaker statement, and it is the one the named families get
    assert CY.verify_group(table, inverse)["ok"] is True


def test_the_exported_portfolio_is_rebuilt_and_re_counted(tmp_path):
    """The data file is checked when it is read, and a tampered one is refused.

    `data/smallgroups_96.json` is the whole portfolio for K96 — every group of order
    96 — and the export's own invariants are re-counted from each rebuilt table on
    load, so the file cannot disagree with the groups a sweep searches without
    saying so.  A sweep over a *complete* portfolio is only worth anything if the
    file is checked, which is why the check is not optional here.
    """
    path = _portfolio_path(96)
    if not path.exists():
        pytest.skip("no exported portfolio in the repository")
    groups = CY.load_portfolio(path)
    assert len(groups) == 231
    assert {int(g["params"][0]) for g in groups} == {96}
    assert groups[0]["name"] == "SmallGroup(96,1)" and groups[0]["id"] == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["source"]["nr_small_groups"] == 231
    assert payload["checks"] == {"groups": 231, "rebuilt_and_recounted": 231,
                                 "invariant_mismatches": 0,
                                 "signature_classes": payload["checks"]["signature_classes"],
                                 "ambiguous_signature_classes":
                                     payload["checks"]["ambiguous_signature_classes"],
                                 "largest_signature_class":
                                     payload["checks"]["largest_signature_class"]}

    # a declared invariant that the table does not have is refused, and so is a
    # generator list whose closure is a different group
    tampered = copy.deepcopy(payload)
    tampered["groups"][0]["center"] += 1
    bad = tmp_path / "tampered.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="the export declares"):
        CY.load_portfolio(bad)
    swapped = copy.deepcopy(payload)
    swapped["groups"][0]["generators"] = payload["groups"][1]["generators"]
    bad.write_text(json.dumps(swapped), encoding="utf-8")
    with pytest.raises(ValueError, match="the export declares"):
        CY.load_portfolio(bad)


def test_the_order_128_portfolio_is_the_library_list():
    """2328 groups, ids 1..2328, and a sample rebuilt and re-counted anyway.

    Loading the whole portfolio with its invariant check is a minute's work and the
    builder's job (`scripts/portfolio_build.py`); what a *test* has to guard is that
    the committed file is still the list it says it is.  So: the count, the ids, and
    every 97th group closed and re-counted against its own declared invariants — the
    file is data, and data no test ever reads is data that can rot.
    """
    path = _portfolio_path(128)
    if not path.exists():
        pytest.skip("no exported portfolio in the repository")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["order"] == 128 and payload["source"]["nr_small_groups"] == 2328
    groups = payload["groups"]
    assert len(groups) == 2328
    assert [g["id"] for g in groups] == list(range(1, 2329))
    for entry in groups[::97]:
        table, inverse = CY.group_from_description(
            {"family": "permutation", "params": [128, entry["generators"]],
             "name": entry["name"]})
        assert len(table) == 128
        assert CY.portfolio_signature(table, inverse) == {
            key: entry[key] for key in ("orders", "classes", "center", "derived",
                                        "exponent", "abelian")}


def test_the_sweep_takes_its_portfolio_from_an_export(tmp_path):
    """`--portfolio` is the same sweep over a list it did not build itself.

    The hunt checks every table before it searches anything, and a portfolio read from
    a file is rebuilt by the loader; this is that path end to end, on a one-group file
    whose group is not in any named family — with the row still naming the group it
    came from, because a row that says only "some group" is not evidence.
    """
    if not SOLVER:
        pytest.skip("no bundled SAT solver")
    description = {"family": "permutation", "params": [6, [[1, 0, 2], [1, 2, 0]]],
                   "name": "SmallGroup(6,1)"}
    table, inverse = CY.group_from_description(description)
    portfolio = {"what": "test", "order": 6, "source": {"nr_small_groups": 1},
                 "groups": [{"id": 1, "name": "SmallGroup(6,1)", "degree": 3,
                             "generators": description["params"][1],
                             **CY.portfolio_signature(table, inverse)}]}
    path = tmp_path / "smallgroups_6.json"
    path.write_text(json.dumps(portfolio), encoding="utf-8")
    out = tmp_path / "rows.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "cayley_hunt.py"
    result = subprocess.run(
        [sys.executable, str(script), "6:3,3", "--portfolio", str(path),
         "--seconds", "30", "--workers", "1", "--json", str(out)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 groups" in result.stdout
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 1
    row, = rows
    assert row["name"] == "SmallGroup(6,1)" and row["n"] == 6 and row["sizes"] == [3, 3]
    assert row["group"]["family"] == "permutation"
    assert row["status"] == "unsat"          # R(3,3) = 6, over this group too
    assert row["num_vars"] and row["num_clauses"]
    # the portfolio is for one order: a sweep at another order is refused
    result = subprocess.run(
        [sys.executable, str(script), "12:3,3", "--portfolio", str(path),
         "--seconds", "5"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "not 12" in result.stderr


def test_an_imported_group_can_be_certified_and_verified(tmp_path):
    """The whole path on a library group: select, decide, then re-derive.

    ``oplab cayley --portfolio`` picks a group the named families do not build and
    decides it arithmetically here (96 = 2^5 * 3, so the group has an element of
    order 3 and every colour forbidding a triangle is out), and the verifier then
    rebuilds that group from the permutation generators the certificate carries —
    including the stored multiplication table, which is what makes the claim about
    the group rather than about its name.
    """
    from oplab.cli import main

    path = _portfolio_path(96)
    if not path.exists():
        pytest.skip("no exported portfolio in the repository")
    out = tmp_path / "k96_small1.json"
    assert main(["cayley", "--n", "96", "--sizes", "3,3,3", "--portfolio", str(path),
                 "--group", "SmallGroup(96,1)", "--out", str(out)]) == 0
    cert = json.loads(out.read_text(encoding="utf-8"))
    assert cert["payload"]["status"] == "obstructed"
    assert cert["payload"]["group"]["family"] == "permutation"
    assert len(cert["payload"]["table"]) == 96
    result = verify_certificate(cert)
    assert result["ok"], result.get("reason")
    assert "element of order 3" in result["establishes"]

    # the stored table is part of the claim: one wrong entry is refused, even though
    # the description would still describe a perfectly good group
    forged = copy.deepcopy(cert)
    forged["payload"]["table"][7][9] = (forged["payload"]["table"][7][9] + 1) % 96
    forged["payload_sha256"] = payload_hash(forged["payload"])
    result = verify_certificate(forged)
    assert not result["ok"] and "stored multiplication table" in result["reason"]


def test_the_cli_lists_and_refuses_an_export_of_another_order(capsys):
    """`--list` is how a group is named, and the order in the file is binding.

    A portfolio is for one order; the CLI has to refuse one for another order rather
    than silently searching the wrong list, and it has to be able to name the groups
    so a certificate can be written from a command line.
    """
    from oplab.cli import main

    path = _portfolio_path(96)
    if not path.exists():
        pytest.skip("no exported portfolio in the repository")
    assert main(["cayley", "--n", "96", "--portfolio", str(path), "--list"]) == 0
    listing = capsys.readouterr().out
    assert "SmallGroup(96,1)" in listing and listing.count("\n") == 231
    assert main(["cayley", "--n", "128", "--portfolio", str(path), "--list"]) == 2
    assert "not 128" in capsys.readouterr().err
