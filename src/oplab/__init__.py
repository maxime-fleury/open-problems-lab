"""open-problems-lab: reproducible attacks on open problems, plus verifiers.

The design rule of the package: **generation and verification are separate**.
Search code writes certificates (plain JSON) into ``certs/``; ``oplab.verify``
re-derives every claimed quantity from the raw data in the certificate, so a
claim is never taken from the file at face value.
"""

from __future__ import annotations

__version__ = "0.1.0"

SCHEMA_VERSION = 1
