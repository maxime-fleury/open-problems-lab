#!/usr/bin/env python3
"""Write the README's BibTeX citation from ``CITATION.cff``.

    python scripts/gen_citation.py            # rewrite the block in README.md
    python scripts/gen_citation.py --check    # fail when the block is stale

``CITATION.cff`` is what a citation manager reads and the README is where a human
looks, so the two have to say the same thing.  The repository's licence makes that
more than tidiness: the citation is the *only* condition CC BY 4.0 attaches here
(NOTICE spells it out), so a citation that has drifted — a version bump, a renamed
author, a moved repository URL — is a licence problem and not a cosmetic one.  The
block between the two markers in README.md is therefore generated and never edited
by hand, and `--check` (which the test suite runs) fails when it and the `.cff`
disagree.

The `.cff` is read by a *subset* parser: it understands the flat `key: value` lines
and the flat lists that CITATION.cff is made of, and it raises on anything else
rather than guessing.  A YAML dependency for a handful of fields would be heavier
than the file it reads, and a silent mis-read would publish a citation pointing at
something else, which is a worse failure than the one it avoids.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# the fence this file owns in README.md; everything between them is rewritten
BEGIN = "<!-- citation:begin (generated: scripts/gen_citation.py) -->"
END = "<!-- citation:end -->"

# what the entry must be built from, and where each of them comes from
REQUIRED = ("title", "authors", "license", "repository-code")
_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")


def _scalar(text: str) -> str:
    """A scalar as written, with one layer of quotes taken off."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def read_cff(path: Path) -> dict[str, object]:
    """The flat fields of a `.cff`, or an error naming the line it could not read.

    Only two shapes are understood: `key: value` and `key:` followed by `- item`
    lines, where an item is either a scalar or a single `name: value` pair.  That is
    everything CITATION.cff uses, and refusing the rest is the point — a nested
    structure read as flat would produce a citation with the wrong author in it.
    """
    fields: dict[str, object] = {}
    pending: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if pending is None:
                raise SystemExit(f"{path}:{number}: a list item outside a list")
            item = line[4:].strip()
            key, separator, value = item.partition(": ")
            if separator and _KEY.match(key):
                fields[pending].append({key: _scalar(value)})  # type: ignore[union-attr]
            else:
                fields[pending].append(_scalar(item))  # type: ignore[union-attr]
            continue
        if line[0] in " \t":
            raise SystemExit(f"{path}:{number}: this reader takes flat keys and flat "
                             f"lists only, and this line is neither")
        key, separator, value = line.partition(":")
        if not separator or not _KEY.match(key.strip()):
            raise SystemExit(f"{path}:{number}: not a `key: value` line")
        key, value = key.strip(), value.strip()
        pending = None
        if value:
            fields[key] = _scalar(value)
        else:
            fields[key] = []
            pending = key
    return fields


def bibtex(fields: dict[str, object]) -> str:
    """The `@software` entry, from the fields a citation actually needs.

    The title is wrapped in braces so that a citation stylesheet cannot lower-case
    it, and the key is the repository's own name, so two projects cited from their
    `.cff` do not collide in one bibliography.
    """
    missing = [key for key in REQUIRED if not fields.get(key)]
    if missing:
        raise SystemExit(f"CITATION.cff carries no {', '.join(missing)}: a citation "
                         f"without them would be wrong rather than incomplete")
    authors: list[str] = []
    for entry in fields["authors"]:  # type: ignore[union-attr]
        if not isinstance(entry, dict) or "name" not in entry:
            raise SystemExit(f"authors are read as `- name: …`, and this reader found "
                             f"{entry!r}; extend it, or keep CITATION.cff in that shape")
        authors.append(str(entry["name"]))
    released = str(fields.get("date-released", ""))
    if len(released) < 4 or not released[:4].isdigit():
        raise SystemExit("CITATION.cff has no `date-released: YYYY-MM-DD` to take the "
                         "year from")
    url = str(fields["repository-code"])
    rows = [
        ("author", " and ".join(authors)),
        ("title", "{" + str(fields["title"]) + "}"),
        ("year", released[:4]),
        ("version", fields.get("version")),
        ("license", fields["license"]),
        ("url", url),
        ("note", "Citing this repository is the only condition its licence asks for; "
                 "the reference values it compares against are listed in docs/targets.md."),
    ]
    filled = [(name, str(value)) for name, value in rows if value]
    width = max(len(name) for name, _ in filled)
    body = "\n".join(f"  {name.ljust(width)} = {{{value}}},"
                     for name, value in filled[:-1])
    tail = filled[-1]
    return (f"@software{{{Path(url.rstrip('/')).name},\n{body}\n"
            f"  {tail[0].ljust(width)} = {{{tail[1]}}}\n}}")


def render(readme: str, block: str) -> str:
    """`README.md` with the generated block in place, whatever it held before.

    The result depends only on the two marker lines and the block, so running this
    twice changes nothing and `--check` is a plain string comparison.
    """
    start, end = readme.find(BEGIN), readme.find(END)
    if start < 0 or end < 0 or end < start:
        raise SystemExit(f"README.md has no `{BEGIN}` ... `{END}` block to write into")
    return f"{readme[:start + len(BEGIN)]}\n{block}{readme[end:]}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="write nothing: fail when README.md is not what this "
                             "would write (the test suite runs this)")
    parser.add_argument("--cff", default=str(ROOT / "CITATION.cff"),
                        help="the machine-readable citation to read")
    parser.add_argument("--readme", default=str(ROOT / "README.md"),
                        help="the file holding the generated block")
    args = parser.parse_args(argv)

    cff, readme = Path(args.cff), Path(args.readme)
    block = f"```bibtex\n{bibtex(read_cff(cff))}\n```\n"
    current = readme.read_text(encoding="utf-8")
    wanted = render(current, block)
    if args.check:
        if wanted != current:
            print(f"{readme}: the citation block is not what {cff.name} says; run "
                  f"`python scripts/gen_citation.py`", file=sys.stderr)
            return 1
        print(f"{readme}: the citation matches {cff.name}")
        return 0
    if wanted == current:
        print(f"{readme}: the citation already matches {cff.name}")
        return 0
    readme.write_text(wanted, encoding="utf-8", newline="\n")
    print(f"{readme}: citation written from {cff.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
