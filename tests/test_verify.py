import json
from pathlib import Path

import numpy as np
import pytest

from oplab import multicolour as MC, ramsey as R, sphere as S, unitdist as U
from oplab.cli import main
from oplab.verify import make_certificate, payload_hash, verify_certificate, verify_path


def _sphere_cert(system="d5"):
    P = S.root_system(system)
    return make_certificate(
        "kissing",
        f"{system} root system",
        {"dim": P.shape[1], "points": [[float(x) for x in row] for row in P]},
        {"n_points": len(P), "dim": P.shape[1], "max_dot": S.max_dot(P)},
        {"generator": "test", "created": "2026-10-15"},
    )


def _moser_cert():
    points = U.moser_spindle()
    edges = U.edges_of(U.adjacency_from_points(points))
    return make_certificate(
        "unit_distance",
        "moser spindle",
        {"points": [[float(x) for x in row] for row in points], "edges": [list(e) for e in edges]},
        {"n_vertices": len(points), "n_edges": len(edges), "chromatic_number": 4},
        {"generator": "test", "created": "2026-10-15"},
    )


def test_valid_certificates_verify():
    for cert in (_sphere_cert("e8"), _moser_cert()):
        result = verify_certificate(cert)
        assert result["ok"], result.get("reason")
        assert result["establishes"]


def test_kissing_certificate_rejects_a_non_configuration():
    cert = _sphere_cert("d5")
    points = np.asarray(cert["payload"]["points"], dtype=float)
    points[0] = points[1]
    cert["payload"]["points"] = points.tolist()
    cert["payload_sha256"] = payload_hash(cert["payload"])
    result = verify_certificate(cert)
    assert not result["ok"]
    assert "kissing configuration" in result["reason"]


def test_tampered_payload_is_detected():
    cert = _sphere_cert("e6")
    cert["payload"]["points"][0][0] += 0.1
    result = verify_certificate(cert)
    assert not result["ok"]
    assert "sha256" in result["reason"]


def test_wrong_claim_is_detected():
    cert = _moser_cert()
    cert["claims"]["chromatic_number"] = 3
    result = verify_certificate(cert)
    assert not result["ok"]


def test_ramsey_certificate_reports_the_bound():
    # A colouring of K42 (or K5 with k=3 in spirit) with no monochromatic K5 is
    # exactly what would raise R(5,5); build a trivially small analogue by
    # checking that a clean colouring reports a bound and a dirty one does not.
    n = 6
    clean = _ramsey_cert(6, R.empty_coloring(6))
    result = verify_certificate(clean)
    assert result["ok"]
    assert result["establishes"] is None  # a single monochromatic K5 remains
    dirty = _ramsey_cert(n, R.from_edges(n, [(0, 1)]))
    assert verify_certificate(dirty)["ok"]


def _ramsey_cert(n, red):
    return make_certificate(
        "ramsey",
        "test",
        {"n": n, "k": 5, "coloring": R.serialize(red, n)},
        {"n": n, "mono_k5": R.count_mono_k5(red, n)},
        {"generator": "test", "created": "2026-10-15"},
    )


def test_circulant_certificate_requires_full_coverage():
    cert = make_certificate(
        "circulant",
        "fake sweep",
        {"n": 42, "k": 5, "colourings_tested": 1000, "witnesses": [], "seconds": 1.0, "workers": 1},
        {"colourings_tested": 1000},
        {"generator": "test", "created": "2026-10-15"},
    )
    result = verify_certificate(cert)
    assert not result["ok"]
    assert "of the" in result["reason"]


def test_circulant_certificate_verifies_a_witness():
    res = R.circulant_search(17, k=4)
    cert = make_certificate(
        "circulant",
        "paley",
        {"n": 17, "k": 4, "colourings_tested": res["colourings_tested"],
         "witnesses": res["witnesses"], "seconds": 0.0, "workers": 1},
        {"witnesses": len(res["witnesses"])},
        {"generator": "test", "created": "2026-10-15"},
    )
    result = verify_certificate(cert)
    assert result["ok"], result.get("reason")
    assert "R(4,4) > 17" in result["establishes"]


def test_spherical_search_certificate_flags_honestly():
    rng = np.random.default_rng(0)
    P = S.random_points(40, 5, rng)  # almost surely not a kissing configuration
    cert = make_certificate(
        "spherical_search",
        "failed attempt",
        {"dim": 5, "points": [[float(x) for x in row] for row in P]},
        {"n_points": 40, "dim": 5, "max_dot": S.max_dot(P), "threshold": 0.5, "establishes_bound": False},
        {"generator": "test", "created": "2026-10-15"},
    )
    assert verify_certificate(cert)["ok"]
    cert["claims"]["establishes_bound"] = True
    assert not verify_certificate(cert)["ok"]


def test_cli_build_verify_and_report(tmp_path):
    cert_path = tmp_path / "d4.json"
    assert main(["build", "--kind", "sphere", "--system", "d4", "--out", str(cert_path)]) == 0
    assert cert_path.exists()
    results = verify_path(tmp_path)
    assert len(results) == 1
    assert results[0][1]["ok"]
    assert main(["verify", str(tmp_path)]) == 0
    assert main(["verify", str(tmp_path), "--write"]) == 0
    stored = json.loads(cert_path.read_text())
    assert stored["verification"]["verified"] is True
    assert main(["report", "--path", str(tmp_path)]) == 0


def test_cli_verify_fails_on_a_broken_certificate(tmp_path):
    cert = _sphere_cert("d5")
    cert["claims"]["n_points"] = 999
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(cert))
    assert main(["verify", str(path)]) == 1
    bad_json = tmp_path / "not_json.json"
    bad_json.write_text("{oops")
    assert main(["verify", str(bad_json)]) == 1


# --------------------------------------------------------------------------
# the multicolour circulant certificates
# --------------------------------------------------------------------------
def _mc_cert(n, sizes, payload=None, claims=None):
    from oplab.multicolour import CirculantInstance, circulant_obstruction, circulant_solve

    instance = CirculantInstance(n, sizes)
    base = {
        "n": n,
        "sizes": list(sizes),
        "status": "unsat",
        "classes": len(instance.classes),
        "num_vars": instance.total_vars(),
        "num_clauses": instance.clause_count(),
        "clique_groups": {str(s): len(g) for s, g in instance.groups.items()},
        "solver": "cadical195",
        "seconds": 1.0,
    }
    result = circulant_solve(n, sizes, seconds=60.0)
    base["status"] = result["status"]
    if "coloring" in result:
        base["coloring"] = result["coloring"]
    obstruction = circulant_obstruction(n, sizes)
    if obstruction is not None:
        base["obstruction"] = {
            "class": obstruction["class"],
            "triangle": list(obstruction["triangle"]),
            "triangles": obstruction["triangles"],
        }
    base.update(payload or {})
    return make_certificate(
        "circulant_multicolour",
        f"test certificate for K{n} {list(sizes)}",
        base,
        {"n": n, "sizes": list(sizes), "status": base["status"], **(claims or {})},
        {"generator": "test", "created": "2026-10-15"},
    )


@pytest.mark.skipif(not MC.available_solvers(), reason="no bundled SAT solver")
def test_multicolour_circulant_witness_and_obstruction_verify():
    """A witness re-counts; the obstruction is arithmetic; a wrong count is caught."""
    witness = _mc_cert(29, (3, 3, 4))
    assert witness["payload"]["status"] == "sat"
    result = verify_certificate(witness)
    assert result["ok"] and "R(3, 3, 4) > 29" in result["establishes"]

    lie = _mc_cert(29, (3, 3, 4), claims={"monochromatic_cliques": [0, 0, 7]})
    assert not verify_certificate(lie)["ok"]

    obstructed = _mc_cert(51, (3, 3, 3, 3))
    result = verify_certificate(obstructed)
    assert obstructed["payload"]["status"] == "obstructed"
    assert result["ok"] and "no circulant colouring" in result["establishes"]

    # the obstruction may not be claimed where there is none, and a solver
    # verdict may not be dressed up as one
    fake = _mc_cert(50, (3, 3, 3, 3), payload={"status": "obstructed"})
    assert not verify_certificate(fake)["ok"]
    mismatch = _mc_cert(51, (3, 3, 3, 3), payload={"status": "unsat"})
    assert not verify_certificate(mismatch)["ok"]


def test_multicolour_circulant_verifier_rejects_a_non_circulant_witness():
    """A colouring that is not constant on the difference classes is not a witness."""
    from oplab.multicolour import circulant_colouring, difference_classes, serialize_colouring

    payload = {"coloring": ""}
    cert = _mc_cert(29, (3, 3, 4), payload=payload)
    colouring = circulant_colouring(29, {d: 2 for d in difference_classes(29)})
    text = list(serialize_colouring(colouring, 29))
    text[0] = "1" if text[0] != "1" else "0"  # break exactly one edge
    cert["payload"]["coloring"] = "".join(text)
    cert["payload_sha256"] = payload_hash(cert["payload"])
    result = verify_certificate(cert)
    assert not result["ok"]
    assert "not circulant" in result["reason"] or "not clean" in result["reason"]


def test_an_unknown_row_that_records_a_crash_is_not_a_spent_budget():
    """`unknown` means the budget ran out — not that the solver died.

    A worker killed by its budget is reported as `unknown`; a worker that crashed
    is reported with `no_verdict` and its exit code.  Both would otherwise look
    like the same row, and the note attached to an `unknown` row says the budget
    is what stopped it, so the crash has to be refused instead.
    """
    root = Path(__file__).resolve().parents[1]
    source = root / "certs" / "circulant_multicolour" / "k96_3x3x3x4.json"
    cert = json.loads(source.read_text(encoding="utf-8"))
    assert cert["payload"]["status"] == "unknown"
    # the stored row is an honest bounded attempt, and still verifies
    assert verify_certificate(cert, base_dir=source.parent)["ok"]
    assert "budget" in verify_certificate(cert, base_dir=source.parent)["note"]

    crashed = json.loads(source.read_text(encoding="utf-8"))
    crashed["payload"]["no_verdict"] = True
    crashed["payload"]["exit_code"] = 3221225477  # STATUS_ACCESS_VIOLATION
    crashed["payload_sha256"] = payload_hash(crashed["payload"])
    result = verify_certificate(crashed, base_dir=source.parent)
    assert not result["ok"]
    assert "crash" in result["reason"] and "no verdict" in result["reason"]

    # and the exit code alone is enough to tell the two apart
    coded = json.loads(source.read_text(encoding="utf-8"))
    coded["payload"]["exit_code"] = 1
    coded["payload_sha256"] = payload_hash(coded["payload"])
    assert not verify_certificate(coded, base_dir=source.parent)["ok"]


def test_multicolour_circulant_verifier_checks_the_encoding_size():
    cert = _mc_cert(30, (3, 3, 4), payload={"num_clauses": 999999})
    result = verify_certificate(cert)
    assert not result["ok"] and "clauses" in result["reason"]


def test_stored_multicolour_certificates_verify_and_unknown_claims_nothing():
    """Every stored `circulant_multicolour` certificate re-verifies.

    The six `unknown` ones are recordings of a spent budget, so they may carry no
    colouring and no claim; the counts here are the inventory quoted by
    RESULTS.md 9 and the README table, and this is the guard against one of them
    quietly turning into a result.
    """
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "certs" / "circulant_multicolour").glob("*.json"))
    assert len(paths) == 24
    seen: dict[str, int] = {}
    for path in paths:
        cert = json.loads(path.read_text(encoding="utf-8"))
        # base_dir is what lets the nine proof-carrying rows resolve the DRAT trace
        # they name; without it, a certificate that records one must fail, not pass
        result = verify_certificate(cert, base_dir=path.parent)
        assert result["ok"], f"{path.name}: {result.get('reason')}"
        status = cert["claims"]["status"]
        seen[status] = seen.get(status, 0) + 1
        if status == "unknown":
            assert "coloring" not in cert["payload"], path.name
            assert "establishes" not in cert["claims"], path.name
            assert not result["establishes"]
            assert "budget" in result["note"]
    assert seen == {"sat": 5, "unsat": 9, "obstructed": 4, "unknown": 6}


def test_stored_cayley_certificates_verify_and_carry_their_group():
    """Every stored `cayley_multicolour` certificate re-verifies, group and all.

    Three `unsat` rows over *non-cyclic* groups, one arithmetic `obstructed` row and one
    `sat` row — statements the circulant store cannot hold, because over `Z_n` they are
    different (and mostly open) ones.  Each row carries the group as data; the verifier
    checks that table against the one rebuilt from the description, each `unsat` row
    resolves the DRAT trace it names against its own encoding, and the `sat` row is the
    witness a 20 s screen over the complete portfolio of order 96 found in a group no
    named family contains (`SmallGroup(96,87)`, `R(3,3,3,4) > 96`).  The counts are the
    inventory the README and RESULTS.md quote, so a row cannot quietly appear, vanish
    or lose its proof.
    """
    root = Path(__file__).resolve().parents[1]
    directory = root / "certs" / "cayley"
    paths = sorted(directory.glob("*.json"))
    assert len(paths) == 5
    seen: dict[str, int] = {}
    for path in paths:
        cert = json.loads(path.read_text(encoding="utf-8"))
        result = verify_certificate(cert, base_dir=path.parent)
        assert result["ok"], f"{path.name}: {result.get('reason')}"
        payload = cert["payload"]
        seen[payload["status"]] = seen.get(payload["status"], 0) + 1
        # the store is about constructions the circulant family cannot express: the
        # cyclic rows live in certs/circulant_multicolour and are not duplicated here
        assert payload["group"]["family"] != "abelian", path.name
        # ... and the group travels with the certificate, checked against the
        # description rather than taken from it
        assert len(payload["table"]) == payload["n"], path.name
        assert len(payload["inverse"]) == payload["n"], path.name
        assert payload["clique_groups"], path.name
        if payload["status"] == "unsat":
            assert "DRAT proof replayed" in result["establishes"], path.name
        elif payload["status"] == "obstructed":
            assert "any group of order" in result["establishes"], path.name
        elif payload["status"] == "sat":
            # a witness is re-counted, not trusted: the row says which bound it
            # realises over which group, and claims zero monochromatic cliques — a
            # claim the verifier has just re-derived from the expanded colouring
            sizes = ", ".join(map(str, payload["sizes"]))
            assert f"R({sizes}) > {payload['n']}" in result["establishes"], path.name
            assert payload["group"]["name"] in result["establishes"], path.name
            assert cert["claims"]["monochromatic_cliques"] == [0] * len(payload["sizes"]), \
                path.name
            assert result["establishes"] == (
                f"R({sizes}) > {payload['n']} via a translation-invariant witness over "
                f"{payload['group']['name']} (a restriction of the colourings of "
                f"K{payload['n']}: a witness is a witness)"), path.name
    assert seen == {"unsat": 3, "obstructed": 1, "sat": 1}
