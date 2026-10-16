"""The licence is a claim about the repository, so it is checked like the others.

`LICENSE` holds the canonical CC BY 4.0 legal code, and the whole point of shipping
the canonical text is that it stays canonical: a hand-edit, a truncation or a
re-wrapped copy changes what the repository grants while still looking like a licence,
and nothing else in the repository would notice.  The sha256 below is the digest of
`https://creativecommons.org/licenses/by/4.0/legalcode.txt` as published, pinned here
the way the proof store is pinned — and the same digest is recorded in `NOTICE`, where
a reader finds it without reading this file.  The pin is the *working-tree* bytes, so
it rests on `.gitattributes` (`* text=auto eol=lf`): a checkout with CRLF in LICENSE
is a different file, and the test says so instead of hashing two spellings of one.

`NOTICE` carries the two things CC BY 4.0 leaves to the licensor — who the work is
attributed to, and the manner of attribution it asks for, which is a citation of the
repository.  Both are asserted here, together with the SPDX identifier in every file
that carries one, because a relicence that reaches `LICENSE` but not `pyproject.toml`,
`CITATION.cff` or the README is a repository that disagrees with itself.  The notice
lives in its own file rather than in a preamble to `LICENSE` for a measured reason:
GitHub's matcher reads a licence text with anything prepended to it as "Other" rather
than as CC BY 4.0, which is how this was found.

The last test keeps the citation in the README honest, and it is here because the
licence's only condition *is* that citation: a stale entry — a version bump, a renamed
author, a moved URL — would be the one broken thing a user of this work is asked to
repeat.  It calls the generator, so the README is checked against `CITATION.cff` by
the same code that writes it.
"""

from __future__ import annotations

import hashlib
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# the canonical text of CC BY 4.0, as Creative Commons publishes it
CANONICAL_SHA256 = "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"
CANONICAL_BYTES = 18_657
CANONICAL_URL = "https://creativecommons.org/licenses/by/4.0/legalcode.txt"
LICENCE = "CC-BY-4.0"


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_licence_is_the_canonical_cc_by_4_0_text():
    """Byte for byte the published legal code, with its digest pinned here and there.

    The size and the digest catch a customised or truncated text; the anchors catch
    the case where both files were replaced together and consistently — an agreement
    between two wrong files is exactly what a digest of one of them cannot see.
    """
    raw = (ROOT / "LICENSE").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CANONICAL_SHA256, (
        "LICENSE is not the canonical CC BY 4.0 legal code; if the pin is meant to "
        "move, state the new digest here, in NOTICE and in the commit message")
    assert len(raw) == CANONICAL_BYTES
    assert b"\r\n" not in raw, "the canonical text is LF, and the digest assumes it"

    text = raw.decode("utf-8")
    lines = [line.rstrip() for line in text.splitlines()]
    assert lines[0] == "Attribution 4.0 International"
    assert next(line for line in reversed(lines) if line) == \
        "Creative Commons may be contacted at creativecommons.org."
    for anchor in ("Creative Commons Attribution 4.0 International Public License",
                   "Section 2 -- Scope.",
                   "Section 3 -- License Conditions.",
                   "Section 6 -- Term and Termination.",
                   "Section 8 -- Interpretation."):
        assert anchor in text, anchor
    assert "share alike" not in text.lower()
    assert "noncommercial" not in text.lower()


def test_the_notice_names_the_holder_and_the_citation_it_requires():
    """The holder, the identifier, the citation target and the digest that pins it."""
    notice = _text("NOTICE")
    assert "Copyright (c) 2026 maxime-fleury" in notice
    assert f"SPDX-License-Identifier: {LICENCE}" in notice
    assert "https://github.com/maxime-fleury/open-problems-lab" in notice
    # the attribution clause the notice is specifying, quoted in full
    assert "section 3(a)(1)" in notice
    # the digest a reader can check the file against without reading the tests
    assert CANONICAL_SHA256 in notice
    assert CANONICAL_URL in notice
    # and the split is what makes the file authoritative
    assert "not a substitute for" in notice


def test_the_spdx_identifier_is_the_same_wherever_it_appears():
    """One licence, named the same way in every file that names it."""
    assert f'license = {{ text = "{LICENCE}" }}' in _text("pyproject.toml")
    assert f"license: {LICENCE}" in _text("CITATION.cff")
    assert LICENCE in _text("NOTICE")
    readme = _text("README.md")
    assert "**CC BY 4.0**" in readme
    for gone in ("MIT — see", "MIT License"):
        assert gone not in readme
    # the .cff is what a citation manager reads; this is the author it will print
    assert 'name: "maxime-fleury"' in _text("CITATION.cff")


def _generator():
    """`scripts/gen_citation.py` as a module, the way the tests call into scripts."""
    scripts = ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module("gen_citation")


def test_the_readme_citation_is_what_citation_cff_generates():
    """The licence's one condition, kept from drifting away from its source."""
    generator = _generator()
    fields = generator.read_cff(ROOT / "CITATION.cff")
    block = f"```bibtex\n{generator.bibtex(fields)}\n```\n"
    readme = _text("README.md")
    assert generator.render(readme, block) == readme, (
        "the README's citation block is stale; run `python scripts/gen_citation.py`")
    assert f"@software{{open-problems-lab," in block
    assert "author  = {maxime-fleury}" in block
    assert "https://github.com/maxime-fleury/open-problems-lab" in block
    assert f"license = {{{LICENCE}}}" in block
    # the generator refuses what it does not understand rather than guessing at it
    assert generator.BEGIN in readme and generator.END in readme


def test_the_citation_generator_reports_staleness_through_its_interface():
    """`--check` is the CI-shaped form of the test above, so it is exercised as a tool.

    A generator that only works when imported is not the interface a contributor or a
    CI job calls, and `--check` must fail rather than rewrite when the two disagree —
    otherwise the check would quietly do its own repair and always pass.
    """
    script = ROOT / "scripts" / "gen_citation.py"
    result = subprocess.run([sys.executable, str(script), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "matches CITATION.cff" in result.stdout

    stale = ROOT / "CITATION.cff"
    original = stale.read_bytes()
    try:
        stale.write_text(original.decode("utf-8").replace("version: 0.1.0",
                                                          "version: 9.9.9"),
                         encoding="utf-8", newline="\n")
        result = subprocess.run([sys.executable, str(script), "--check"],
                                capture_output=True, text=True)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "stale" in result.stderr or "not what CITATION.cff says" in result.stderr
        # it complained and changed nothing
        assert "9.9.9" not in _text("README.md")
    finally:
        stale.write_bytes(original)
