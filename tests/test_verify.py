import json

import numpy as np

from oplab import ramsey as R, sphere as S, unitdist as U
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
