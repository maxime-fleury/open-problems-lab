"""Published reference values, with sources, for the targets of this repo.

Every number here is a *literature* value, never a result of this repository.
Nothing in this file is trusted by the verifiers: certificates are always
re-checked from raw data (see ``oplab.verify``).
"""

from __future__ import annotations

SOURCES = {
    "cohn_kissing": "https://cohn.mit.edu/kissing-numbers/",
    "sloane_packings": "http://neilsloane.com/packings/",
    "cohn_li_2024": "https://arxiv.org/abs/2411.04916",
    "de_laat_2024": "https://arxiv.org/abs/2404.18794",
    "angeltveit_mckay": "https://arxiv.org/abs/2409.15709",
    "exoo_1989": "https://doi.org/10.1002/jgt.3190130114",
    "parts_unit_distance": "https://arxiv.org/abs/2011.05658",
    "de_grey_2018": "https://arxiv.org/abs/1804.02385",
}

#: ``dim -> (best known lower bound, best known upper bound)``.
#: Lower bounds are witnessed by the D5 / E6 / E7 / E8 root configurations for
#: dimensions 5-8 respectively; the only *proved* exact values are 1, 2, 3, 4,
#: 8 and 24 (dimension 8 exact since Cohn-Li 2024).
KISSING_BOUNDS: dict[int, tuple[int, int]] = {
    1: (2, 2),
    2: (6, 6),
    3: (12, 12),
    4: (24, 24),
    5: (40, 44),
    6: (72, 77),
    7: (126, 134),
    8: (240, 240),
}

#: Classical lower-bound configurations, as ``dim -> number of points``.
KISSING_ROOT_CONFIGURATIONS: dict[int, str] = {5: "d5", 6: "e6", 7: "e7", 8: "e8"}

#: Tammes problem on S^2: best known *minimal angular separation*, in degrees,
#: for N = 15..23 (Sloane, "putatively optimal"; the optimum is proved only for
#: N <= 14 and N = 24).
TAMMES_S2_BEST_KNOWN_DEG: dict[int, float] = {
    15: 53.6578501,
    16: 52.2443957,
    17: 51.0903285,
    18: 49.5566548,
    19: 47.6919141,
    20: 47.4310362,
    21: 45.6132231,
    22: 44.7401612,
    23: 43.7099642,
}

#: Ramsey number R(5,5): best known bounds.  ``R(5,5) >= 43`` since Exoo 1989
#: (a 2-colouring of K42 without a monochromatic K5); ``R(5,5) <= 46`` from
#: Angeltveit & McKay (2024).  A colouring of K43 without a monochromatic K5
#: would raise the lower bound to 44 and would be a 1989-to-now breakthrough.
RAMSEY_R55_BOUNDS: tuple[int, int] = (43, 46)

#: Smallest known 5-chromatic unit-distance graph (Jaan Parts); no 6-chromatic
#: unit-distance graph is known, and the chromatic number of the plane is known
#: only to lie in ``5 <= chi <= 7``.
SMALLEST_KNOWN_5_CHROMATIC_UNIT_DISTANCE_VERTICES = 509
PLANE_CHROMATIC_BOUNDS: tuple[int, int] = (5, 7)

#: Smallest 4-chromatic unit-distance graph: the Moser spindle (7 vertices,
#: 11 edges), proved minimal.
SMALLEST_4_CHROMATIC_UNIT_DISTANCE_VERTICES = 7
