"""Tests for the cube-and-conquer driver.

The driver's job is to make a claim that is exactly as strong as its evidence, so
the tests are about the two halves of that claim: the **cover check** (a cube list
is a complete decision tree, or nothing is claimed) and the **witness path** (a
satisfiable leaf is decoded with the instance class and re-counted by
``verify_colouring`` before it is called a witness).

No external tool is needed here: ``march_cu`` is replaced by a cube file written by
hand, and the solver by a stub command, which is also how the failure paths — a
leaf the engine says nothing about, a leaf that makes the run incomplete — stay
deterministic instead of depending on a budget.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from oplab import multicolour as MC  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cube_conquer import (  # noqa: E402
    combine_reports,
    cube_cover,
    parse_spec,
    read_cubes,
    report_path,
    write_cubes,
)


def _script_module():
    """The driver as a module, for the tests that call into it."""
    return importlib.import_module("cube_conquer")


def test_a_cube_file_is_read_in_both_shapes_and_ignores_what_is_not_a_cube(tmp_path):
    """``march_cu`` writes ``a <lits> 0``; a bare literal list is the same cube.

    Everything else in the file — comments, the header, a solver's answer — is not a
    cube, and reading one as a cube would put a phantom leaf into the cover.
    """
    path = tmp_path / "mixed.icnf"
    path.write_text(
        "c a comment\n"
        "p cnf 6 0\n"
        "a 1 -2 3 0\n"
        "4 5 -6 0\n"
        "s SATISFIABLE\n"
        "v 1 2 3 0\n"
        "a -1 2 -3 0\n",
        encoding="ascii",
    )
    assert read_cubes(path) == [[1, -2, 3], [4, 5, -6], [-1, 2, -3]]

    written = write_cubes(tmp_path / "out.icnf", [[1, -2], [1, 2]])
    assert read_cubes(written) == [[1, -2], [1, 2]]


def test_only_a_complete_decision_tree_is_a_cover():
    """The check that stands between "every leaf I looked at" and "the instance".

    A full tree at depth two is a cover; the same list with one leaf removed is not;
    cubes of different lengths, a cube that lists a variable twice, and siblings that
    are not one variable in both signs are each enough to refuse it.
    """
    complete = cube_cover([[1, 2], [1, -2], [-1, 2], [-1, -2]])
    assert complete == {"complete": True, "cubes": 4, "leaves": 4, "depth": 2}

    # different variables in different *subtrees* is a tree, and still a cover
    assert cube_cover([[1, 2], [1, -2], [-1, 3], [-1, -3]])["complete"] is True

    missing = cube_cover([[1, 2], [1, -2], [-1, 2]])
    assert missing["complete"] is False and "does not branch" in missing["reason"]

    ragged = cube_cover([[1, 2], [1, -2], [-1], [-1, -2]])
    assert ragged["complete"] is False and "different lengths" in ragged["reason"]

    repeated = cube_cover([[1, 2], [1, -2], [-1, 1], [-1, -2]])
    assert repeated["complete"] is False and "repeats a variable" in repeated["reason"]

    empty = cube_cover([])
    assert empty["complete"] is False and empty["cubes"] == 0


def test_a_cover_that_lost_one_leaf_is_refused():
    """Dropping one leaf of a depth-3 cover: the trie test has to notice.

    This is the failure the check exists for — 7 of 8 leaves refuted is not a
    refutation — and the reason has to say how many leaves were found.
    """
    cover = [[a, b, c] for a in (1, -1) for b in (2, -2) for c in (3, -3)]
    assert cube_cover(cover)["complete"] is True
    damaged = cube_cover(cover[:-1])
    assert damaged["complete"] is False
    # the missing leaf shows up as its parent having one child, and the reason says
    # how much of the tree was complete before that was noticed
    assert "does not branch" in damaged["reason"]
    assert damaged["leaves"] < 8, damaged


def test_the_instance_spec_is_the_same_shape_the_other_scripts_take():
    assert parse_spec("97:3,3,3,4") == (97, (3, 3, 3, 4))
    assert parse_spec("18:4,4") == (18, (4, 4))
    with pytest.raises(SystemExit):
        parse_spec("97")


# --------------------------------------------------------------------------
# the witness path, and the ways a run stays honest about not deciding
# --------------------------------------------------------------------------
def _stub_command(tmp_path: Path, body: str) -> str:
    """A stand-in engine, quoted, because an interpreter path may contain a space."""
    path = tmp_path / "stub_engine.py"
    path.write_text(body, encoding="utf-8")
    return f'"{sys.executable}" "{path}"'


def _run(tmp_path: Path, *args, engine: str) -> tuple[int, dict | None]:
    """Run the driver as a user does, and read the report it leaves behind."""
    out = tmp_path / "report.json"
    command = [sys.executable, str(ROOT / "scripts" / "cube_conquer.py"), *args,
               "--out", str(out), "--workdir", str(tmp_path / "work")]
    env = {**os.environ, "OPLAB_KISSAT": engine}
    done = subprocess.run(command, capture_output=True, text=True, env=env, cwd=ROOT)
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return done.returncode, report


def test_a_leaf_the_engine_will_not_decide_leaves_the_run_incomplete(tmp_path):
    """Silence is not a refutation: the run claims nothing and hands back the cubes.

    The engine answers nothing at all, which is the shape of a spent budget, so every
    leaf is ``unknown``; the report has to carry the undecided cubes in a file a
    second pass can be pointed at, and the exit status has to refuse the claim.
    """
    cubes = tmp_path / "cubes.icnf"
    write_cubes(cubes, [[1, 2], [1, -2], [-1, 2], [-1, -2]])
    engine = _stub_command(tmp_path, "import sys\nsys.exit(0)\n")
    code, report = _run(tmp_path, "5:3,3", "--cubes", str(cubes), "--depth", "2",
                        "--budget", "10", "--workers", "2", engine=engine)
    assert code == 2, report
    assert report["verdict"] == "incomplete"
    assert report["counts"] == {"unknown": 4}
    assert report["unresolved"] == 4 and report["cover"]["complete"] is True
    assert "nothing" in report["establishes"]
    # in the order of the cube file, not in the order the shards happened to finish
    assert read_cubes(report["unresolved_file"]) == [[1, 2], [1, -2], [-1, 2], [-1, -2]]


def test_a_cover_whose_every_leaf_is_refuted_is_reported_as_just_that(tmp_path):
    """A closed cover with every leaf refuted, and no more than that.

    What was established is the refutation, and what it rests on — verdicts rather
    than proofs — is in the report, because a run that quietly upgraded its own
    evidence would be the one thing this repository cannot ship.
    """
    cubes = tmp_path / "cubes.icnf"
    write_cubes(cubes, [[1, 2], [1, -2], [-1, 2], [-1, -2]])
    engine = _stub_command(tmp_path, "print('s UNSATISFIABLE')\n")
    code, report = _run(tmp_path, "5:3,3", "--cubes", str(cubes), "--depth", "2",
                        "--budget", "10", "--workers", "2", engine=engine)
    assert code == 0, report
    assert report["verdict"] == "refuted-cover"
    assert report["counts"] == {"unsat": 4}
    assert "solver verdicts, not proofs" in report["establishes"]
    assert report["engine"]["backing"] == "binary" and report["engine"]["name"] == "kissat404"
    assert "witness" not in report


def test_a_fragment_is_reported_as_a_fragment(tmp_path):
    """A cube list handed in with ``--cubes`` need not be a cover, and is not sold as one.

    Refuting part of a cover is a real result about that part; calling it a
    refutation of the instance is the mistake the two verdict names exist to prevent.
    """
    cubes = tmp_path / "fragment.icnf"
    write_cubes(cubes, [[1, 2], [1, -2]])  # one node's two children, not a cover
    engine = _stub_command(tmp_path, "print('s UNSATISFIABLE')\n")
    code, report = _run(tmp_path, "5:3,3", "--cubes", str(cubes), "--depth", "2",
                        "--budget", "10", "--workers", "2", engine=engine)
    assert code == 0, report
    assert report["verdict"] == "refuted-fragment"
    assert report["cover"]["complete"] is False
    assert "a fragment of a cover, not a cover" in report["establishes"]


def test_a_list_that_does_not_close_is_never_called_a_refutation_of_the_instance(tmp_path):
    """An open cube list is reported as the piece it is, whatever happened to its leaves.

    Every leaf refuted and the list open adds up to a fragment: the report says a
    fragment and never that the instance is refuted, and the cover block carries the
    reason the list is open.  (A second pass over the undecided leaves of a cover is
    exactly such a fragment, which is why this is a verdict and not a refusal.)
    """
    cubes = tmp_path / "open.icnf"
    write_cubes(cubes, [[1, 2], [1, -2], [-1, 2]])  # -1,-2 is missing
    engine = _stub_command(tmp_path, "print('s UNSATISFIABLE')\n")
    code, report = _run(tmp_path, "5:3,3", "--cubes", str(cubes), "--depth", "2",
                        "--budget", "10", "--workers", "2", engine=engine)
    assert code == 0 and report["verdict"] == "refuted-fragment", report
    assert report["cover"]["complete"] is False
    assert "does not branch" in report["cover"]["reason"]
    assert "not a cover" in report["establishes"]
    assert "no colouring of K5" not in report["establishes"]
    assert "witness" not in report


# --------------------------------------------------------------------------
# combining passes: the claim no single pass can make
# --------------------------------------------------------------------------
def _rows_file(rows_dir: Path, rows: list[dict], shard: int = 0) -> Path:
    """The rows a run leaves behind, one line per leaf, in the shape it writes them."""
    rows_dir.mkdir(parents=True, exist_ok=True)
    path = rows_dir / f"shard_{shard:03d}.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _report(tmp_path: Path, name: str, cube_file, rows_dir, *, n=5, sizes=(3, 3),
            budget=10.0, clauses=12, verdict_rows=()) -> Path:
    """A pass, as a report on disk: what ``combine_reports`` reads and nothing more.

    Handing these in rather than running a solver is what makes the refusals
    testable: a pass that contradicts another is exactly the case a solver would not
    produce on demand.
    """
    _rows_file(rows_dir, [{"index": index + 1, "cube": list(cube), "status": status}
                          for index, (cube, status) in enumerate(verdict_rows)])
    path = tmp_path / name
    path.write_text(json.dumps({
        "n": n, "sizes": list(sizes),
        "encoding": {"num_vars": 10, "num_clauses": clauses},
        "cubing": {"cubes_file": str(cube_file)},
        "rows_dir": str(rows_dir),
        "engine": {"name": "kissat404", "backing": "binary", "budget_seconds": budget},
        "shards": 3.0,
    }), encoding="utf-8")
    return path


def test_the_second_pass_is_what_makes_the_first_one_a_refutation(tmp_path):
    """Neither report may claim the refutation; combining them may, and the budget
    that ran out in the first pass is not a disagreement with the second.

    The cover is refuted 3 leaves + 1 leaf: pass one says nothing about the last one
    (its budget ran out), pass two refutes it.  That is the shape of the ``K97`` run,
    and the report that comes out has to be a ``refuted-cover`` with all four leaves.
    """
    cover = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
    cubes = tmp_path / "cover.icnf"
    write_cubes(cubes, cover)
    resolver = tmp_path / "resumed.icnf"
    write_cubes(resolver, [cover[-1]])
    first = _report(tmp_path, "first.json", cubes, tmp_path / "r1",
                    verdict_rows=[(c, "unsat") for c in cover[:3]]
                                 + [(cover[-1], "unknown")])
    second = _report(tmp_path, "second.json", resolver, tmp_path / "r2", budget=900.0,
                     verdict_rows=[(cover[-1], "unsat")])

    report = combine_reports([str(first), str(second)])
    assert report["verdict"] == "refuted-cover", report
    assert report["counts"] == {"unsat": 4} and report["decided"] == 4
    assert report["unresolved"] == 0 and report["errors"] == 0
    assert report["cover"] == {"complete": True, "cubes": 4, "leaves": 4, "depth": 2}
    assert "solver verdicts and not proofs" in report["establishes"]
    assert [source["budget_seconds"] for source in report["sources"]] == [10.0, 900.0]
    # the claim says how each leaf was refuted, not only that it was
    assert "at 10 s per leaf refuted 3" in report["establishes"]
    assert "at 900 s per leaf refuted 1" in report["establishes"]


def test_a_leaf_no_pass_decided_stops_the_claim(tmp_path):
    """Four leaves, three refuted: the combination is a fragment, not a cover."""
    cover = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
    cubes = tmp_path / "cover.icnf"
    write_cubes(cubes, cover)
    first = _report(tmp_path, "first.json", cubes, tmp_path / "r1",
                    verdict_rows=[(c, "unsat") for c in cover[:3]]
                                 + [(cover[-1], "unknown")])

    report = combine_reports([str(first)])
    assert report["verdict"] == "incomplete", report
    assert report["unresolved"] == 1 and report["counts"] == {"unsat": 3, "unknown": 1}
    assert "1 of 4 leaves were left undecided" in report["establishes"]

    # and a cube list that does not close is not a cover for the leaves to belong to
    partial = tmp_path / "partial.icnf"
    write_cubes(partial, [[1, 2], [1, -2], [-1, 2]])
    fragment = _report(tmp_path, "fragment.json", partial, tmp_path / "r3",
                       verdict_rows=[(c, "unsat") for c in [[1, 2], [1, -2], [-1, 2]]])
    refused = combine_reports([str(fragment)])
    assert refused["verdict"] == "incomplete"
    assert "no cover" in refused["establishes"]


def test_two_passes_that_contradict_each_other_are_refused(tmp_path):
    """Two answers about one leaf cannot both be right, and neither is picked.

    A pass may supersede a budget that ran out — that is the point of combining —
    but not another pass's verdict, and a cube a pass decided that is not even a leaf
    of the cover means the passes are not about one partition.
    """
    cover = [[1, 2], [1, -2], [-1, 2], [-1, -2]]
    cubes = tmp_path / "cover.icnf"
    write_cubes(cubes, cover)
    first = _report(tmp_path, "first.json", cubes, tmp_path / "r1",
                    verdict_rows=[(c, "unsat") for c in cover])
    contradictory = tmp_path / "again.icnf"
    write_cubes(contradictory, [cover[0]])
    second = _report(tmp_path, "second.json", contradictory, tmp_path / "r2",
                     verdict_rows=[(cover[0], "sat")])
    report = combine_reports([str(first), str(second)])
    assert report["verdict"] == "conflict", report
    assert "different verdicts" in report["establishes"]

    elsewhere = tmp_path / "elsewhere.icnf"
    write_cubes(elsewhere, [[3, 4], [3, -4], [-3, 4], [-3, -4]])
    third = _report(tmp_path, "third.json", elsewhere, tmp_path / "r3",
                    verdict_rows=[(c, "unsat") for c in [[3, 4], [3, -4], [-3, 4], [-3, -4]]])
    stray = combine_reports([str(first), str(third)])
    assert stray["verdict"] == "incomplete"
    assert "not leaves of the cover" in stray["establishes"]

    other_instance = _report(tmp_path, "other.json", cubes, tmp_path / "r4", n=6,
                             verdict_rows=[(c, "unsat") for c in cover])
    mismatched = combine_reports([str(first), str(other_instance)])
    assert mismatched["verdict"] == "incomplete"
    assert "is about K6" in mismatched["establishes"]


def test_a_report_written_on_another_platform_is_still_readable():
    """A committed report carries the separators of the machine that wrote it.

    ``runs\\cube_k97_d12\\k97_d12.icnf`` is one file *name* on Linux, so a report that
    only its author's platform can re-read is half a record — which is exactly what
    the CI job that re-reads the committed passes would hit.  Separators are
    rewritten; an absolute path from the other platform is left alone, since it names
    where the input *was* rather than something that can be opened here.
    """
    assert report_path("runs\\cube_k97_d12\\k97_d12.icnf").as_posix() == \
        "runs/cube_k97_d12/k97_d12.icnf"
    assert report_path("runs/cube_k97_d12/rows").as_posix() == "runs/cube_k97_d12/rows"
    assert report_path("/tmp/k97.icnf").as_posix() == "/tmp/k97.icnf"
    assert report_path("D:\\gen\\x.cnf").as_posix() == "D:/gen/x.cnf"


def test_a_resumed_pass_is_combined_through_the_command_line(tmp_path):
    """The two passes as a user runs them, then ``--combine`` over both reports.

    The engine refuses exactly one leaf — the cube whose units are ``-1`` and ``2`` —
    so the first pass comes back ``incomplete`` and hands that leaf out; the second
    pass refutes it.  Neither exit status is 0, and the combined one is.
    """
    cubes = tmp_path / "cover.icnf"
    write_cubes(cubes, [[1, 2], [1, -2], [-1, 2], [-1, -2]])
    engine = _stub_command(tmp_path, (
        "import sys\n"
        "units = {int(line.split()[0]) for line in open(sys.argv[-1], encoding='ascii')\n"
        "         if len(line.split()) == 2 and line.split()[1] == '0'}\n"
        "if {-1, 2} <= units:\n"
        "    sys.exit(0)          # a spent budget: no verdict at all\n"
        "print('s UNSATISFIABLE')\n"))

    first_out = tmp_path / "first.json"
    command = [sys.executable, str(ROOT / "scripts" / "cube_conquer.py"), "5:3,3",
               "--cubes", str(cubes), "--depth", "2", "--budget", "10", "--workers", "2",
               "--out", str(first_out), "--workdir", str(tmp_path / "w1")]
    done = subprocess.run(command, capture_output=True, text=True,
                          env={**os.environ, "OPLAB_KISSAT": engine}, cwd=ROOT)
    assert done.returncode == 2, done
    first = json.loads(first_out.read_text(encoding="utf-8"))
    assert first["verdict"] == "incomplete" and first["counts"] == {"unsat": 3, "unknown": 1}

    second_out = tmp_path / "second.json"
    command = [sys.executable, str(ROOT / "scripts" / "cube_conquer.py"), "5:3,3",
               "--cubes", first["unresolved_file"], "--depth", "2", "--budget", "10",
               "--workers", "2", "--out", str(second_out), "--workdir", str(tmp_path / "w2")]
    done = subprocess.run(command, capture_output=True, text=True,
                          env={**os.environ, "OPLAB_KISSAT": _stub_command(tmp_path, "print('s UNSATISFIABLE')\n")},
                          cwd=ROOT)
    assert done.returncode == 0, done
    assert json.loads(second_out.read_text(encoding="utf-8"))["verdict"] == "refuted-fragment"

    combined_out = tmp_path / "combined.json"
    command = [sys.executable, str(ROOT / "scripts" / "cube_conquer.py"), "5:3,3",
               "--combine", str(first_out), str(second_out), "--out", str(combined_out)]
    done = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    assert done.returncode == 0, done
    combined = json.loads(combined_out.read_text(encoding="utf-8"))
    assert combined["verdict"] == "refuted-cover" and combined["counts"] == {"unsat": 4}
    assert "cover complete at depth 2" in done.stdout

    # the spec is checked against the reports when it is given, and refused when it
    # is not what they are about
    wrong = subprocess.run([sys.executable, str(ROOT / "scripts" / "cube_conquer.py"),
                            "18:4,4", "--combine", str(first_out), str(second_out),
                            "--out", str(tmp_path / "no.json")],
                           capture_output=True, text=True, cwd=ROOT)
    assert wrong.returncode == 2 and "is not what the reports are about" in wrong.stderr


@pytest.mark.skipif(not _script_module().MC.available_solvers(),
                    reason="no bundled SAT solver to produce a model")
@pytest.mark.skipif(MC.solver_backing("cadical195") != "wheel",
                    reason="python-sat is not installed")
def test_a_satisfiable_leaf_becomes_a_witness_only_after_it_verifies():
    """The witness path, end to end: a model, the instance's decode, and the re-count.

    ``K17`` with sizes ``(4, 4)`` has a stored circulant witness, so a model from a
    solver has to decode to a colouring this repository counts clean — and a
    decodable assignment that is *not* clean (every class in colour 0, which is one
    monochromatic ``K17``) has to be refused rather than written into a report as a
    colouring.
    """
    driver = _script_module()
    instance = driver.MC.CirculantInstance(17, (4, 4))
    solver = driver.MC.solver_class("cadical195")(bootstrap_with=instance.clauses())
    assert solver.solve() is True
    model = solver.get_model()
    solver.delete()

    report: dict = {}
    witness = driver._witness(report, instance, 4, [model[0]], model)
    assert report["verdict"] == "sat"
    assert witness["verify"]["valid"] is True
    assert witness["verify"]["monochromatic_cliques"] == [0, 0]
    assert "R(4, 4) > 17" in report["establishes"]
    assert witness["leaf"] == 4 and witness["coloring"] == instance.decode(model)

    monochrome = [instance.var(d, 0) for d in instance.classes]
    refused = driver._witness(report, instance, 4, [monochrome[0]], monochrome)
    assert report["verdict"] == "sat-invalid"
    assert refused["verify"]["valid"] is False
    assert sum(refused["verify"]["monochromatic_cliques"]) > 0


def test_the_engine_is_refused_when_its_backing_is_not_the_one_asked_for(tmp_path, capsys,
                                                                        monkeypatch):
    """``kissat404`` names a version, and two implementations answer to it.

    Only one of them is usable here, so a campaign can demand the binary — and gets
    stopped before the first leaf when the name would resolve to the wheel instead.
    Both directions are checked without starting an engine or touching a cube file.
    """
    driver = _script_module()
    from oplab import tools
    from oplab.multicolour import solver_backing

    monkeypatch.setattr(tools, "kissat_command", lambda refresh=False: None)
    # Which implementation answers here depends on the machine: the `pysat` wheel
    # where it is installed, and nothing at all where it is not.  The refusal is the
    # same either way, so the test asks which one it *is* rather than assuming the
    # wheel — asserting "wheel" made this pass on a laptop and fail in CI, where the
    # engine package is not installed.
    backing = solver_backing("kissat404")
    assert backing != "binary", "the binary was just monkeypatched away"
    code = driver.main(["5:3,3", "--depth", "2", "--engine-backing", "binary",
                        "--out", str(tmp_path / "refused.json"),
                        "--workdir", str(tmp_path / "w")])
    assert code == 2
    assert f"is backed by {backing}, not binary" in capsys.readouterr().err
    assert not (tmp_path / "refused.json").exists(), "a refused run writes nothing"

    monkeypatch.setattr(tools, "kissat_command", lambda refresh=False: ["kissat"])
    code = driver.main(["5:3,3", "--depth", "2", "--engine-backing", "wheel",
                        "--out", str(tmp_path / "refused2.json"),
                        "--workdir", str(tmp_path / "w2")])
    assert code == 2
    assert "is backed by binary" in capsys.readouterr().err
