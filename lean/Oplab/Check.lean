/-
  Certificate checkers for the Lean layer of open-problems-lab.

  Everything in this file is *hand written* and dependency free (no Mathlib).
  The generated file `Oplab/Certs.lean` imports it and instantiates it with the
  data of `certs/*.json`, so that every claim the Python verifier asserts about
  a certificate can also be checked by the Lean kernel (or by the trusted
  compiler, when the statement is followed by `native_decide`).

  Design rules:

  * Colourings, adjacency and clique counts are combinatorial, so they are
    encoded with exact `Nat` bitmasks and checked with `decide` — no hypothesis,
    no axiom, and no floating point anywhere.
  * Geometric data (points on a sphere, unit-distance drawings) comes from JSON
    as decimal literals.  Those are read as *integers* scaled by a fixed power of
    ten, and the geometric statement is phrased as an exact integer inequality
    with an explicit rounding allowance, so the Lean statement never depends on
    IEEE arithmetic.  The allowance is documented with each certificate.
  * Two independent implementations are provided for the monochromatic-clique
    count: a bitmask recursion (`monoCount`) and a subset enumeration
    (`subsetMonoCount`).  Generated theorems state both, which cross-checks the
    fast path against the naive one.
-/

import Oplab.Basic

set_option maxRecDepth 1000000

/-! ### Basic vector helpers (integer coordinates) -/

/-- Difference of two integer vectors (componentwise). -/
def sub (a b : List Int) : List Int := a.zipWith (fun x y => x - y) b

/-- Squared Euclidean norm of an integer vector. -/
def normSq (v : List Int) : Int := dot v v

/-- Are all vectors of the list pairwise distinct? -/
def distinctVectors (vs : List (List Int)) : Bool :=
  (allPairs vs).all (fun p => !(p.1 == p.2))

/-- Are all squared norms within `tol` of `S` (both scaled integers)? -/
def normsWithin (S tol : Int) (vs : List (List Int)) : Bool :=
  vs.all (fun v => (normSq v - S).natAbs ≤ tol.natAbs)

/-- `cosBelow num den x y`: the cosine of the angle between `x` and `y` is at most
`num / den`, expressed without square roots or division.

For non-positive dot products the bound is automatic (all the certificate
configurations have positive norms); otherwise the exact integer inequality
`den^2 * <x,y>^2 <= num^2 * |x|^2 * |y|^2` is used, which is equivalent to
`cos <= num/den` for positive dot products. -/
def cosBelow (num den : Int) (x y : List Int) : Bool :=
  let d := dot x y
  if d ≤ 0 then true else den * den * (d * d) ≤ num * num * (normSq x * normSq y)

/-- `cosAtLeast num den x y`: same as `cosBelow` with the inequality reversed,
used for the witness pairs of the *failed* configurations. -/
def cosAtLeast (num den : Int) (x y : List Int) : Bool :=
  let d := dot x y
  if d ≤ 0 then false else num * num * (normSq x * normSq y) ≤ den * den * (d * d)

/-- Every pair of the configuration has cosine at most `num / den`. -/
def allCosBelow (num den : Int) (vs : List (List Int)) : Bool :=
  (allPairs vs).all (fun p => cosBelow num den p.1 p.2)

/-! ### Colouring utilities -/

/-- Full vertex mask of `K n`. -/
def fullMask (n : Nat) : Nat := (1 <<< n) - 1

/-- Colour of edge `{u, v}` as a `Bool` (`true` = red), decoded from the canonical
`'0'`/`'1'` string of `n*(n-1)/2` characters in lexicographic edge order. -/
def colourOfChar (n : Nat) (s : List Char) (u v : Nat) : Bool :=
  (s.getD (edgeIndex n (min u v) (max u v)) '1') == '0'

/-- Same, but from the low `n*(n-1)/2` bits of a natural number (`true` = red). -/
def colourOfBits (n m u v : Nat) : Bool :=
  m.testBit (edgeIndex n (min u v) (max u v))

/-- Red adjacency masks of a colouring given by a `'0'`/`'1'` string. -/
def redAdjOfString (n : Nat) (s : List Char) : Nat → Nat :=
  fun u =>
    (List.range n).foldl
      (fun acc v =>
        if u == v then acc
        else if colourOfChar n s u v then acc ||| (1 <<< v) else acc)
      0

/-- Same, for a colouring given by the low bits of a natural number. -/
def redAdjOfBits (n m : Nat) : Nat → Nat :=
  fun u =>
    (List.range n).foldl
      (fun acc v =>
        if u == v then acc
        else if colourOfBits n m u v then acc ||| (1 <<< v) else acc)
      0

/-- Blue adjacency masks, from the red ones. -/
def blueAdjOfRed (n : Nat) (red : Nat → Nat) : Nat → Nat :=
  fun v => fullMask n &&& (fullMask n ^^^ red v)

/-! ### Exact clique counts -/

/-- Exact number of `k`-cliques of the graph `adj` inside the vertex mask `mask`.

Each clique is counted once, at its largest vertex: at vertex `v` the recursion
looks for the remaining `k-1` vertices among `adj v` *below* `v`, which is what
the mask `(1 <<< v) - 1` enforces.  `fuel` makes the recursion total; `k` is
enough fuel because every recursive call lowers `k` by one. -/
def countCliquesFuel (fuel n : Nat) (adj : Nat → Nat) (mask k : Nat) : Nat :=
  match fuel with
  | 0 => 0
  | f + 1 =>
    if k == 0 then 1
    else
      (List.range n).foldl
        (fun acc v =>
          if mask.testBit v then
            acc + countCliquesFuel f n adj (mask &&& adj v &&& ((1 <<< v) - 1)) (k - 1)
          else acc)
        0

/-- Exact number of `k`-cliques inside a mask (see `countCliquesFuel`).  The fuel
is `k + 1`: reaching the base case `k == 0` costs one extra level. -/
def countCliques (n : Nat) (adj : Nat → Nat) (mask k : Nat) : Nat :=
  countCliquesFuel (k + 1) n adj mask k

/-- Exact number of monochromatic `k`-cliques of the colouring encoded by `s`.

This is the machine-checkable content of the Ramsey certificates: the claim
`mono_k5 = 100` becomes `monoCount 42 5 <colouring> = 100`, and a clean
colouring becomes `monoCount n k <colouring> = 0`. -/
def monoCount (n k : Nat) (s : List Char) : Nat :=
  let red := redAdjOfString n s
  countCliques n red (fullMask n) k + countCliques n (blueAdjOfRed n red) (fullMask n) k

/-- Same, for a colouring encoded by the low bits of a natural number. -/
def monoCountBits (n k m : Nat) : Nat :=
  let red := redAdjOfBits n m
  countCliques n red (fullMask n) k + countCliques n (blueAdjOfRed n red) (fullMask n) k

/-! ### A second, independent monochromatic-clique counter -/

/-- All `k`-subsets of `{0, …, n-1}`, as increasing lists.  Structural recursion
on the first argument, so that the kernel can reduce it inside `decide`. -/
def subsetsOfSize : Nat → Nat → List (List Nat)
  | 0, 0 => [[]]
  | 0, _ + 1 => []
  | _ + 1, 0 => [[]]
  | n + 1, k + 1 =>
    subsetsOfSize n (k + 1) ++ (subsetsOfSize n k).map (fun s => s ++ [n])

/-- Does the `k`-subset `t` form a monochromatic clique of the string colouring? -/
def subsetMono (n : Nat) (s : List Char) (t : List Nat) : Bool :=
  match allPairs t with
  | [] => false
  | (x, y) :: rest => rest.all (fun p => colourOfChar n s p.1 p.2 == colourOfChar n s x y)

/-- Same, for the bitmask colouring. -/
def subsetMonoBits (n m : Nat) (t : List Nat) : Bool :=
  match allPairs t with
  | [] => false
  | (x, y) :: rest => rest.all (fun p => colourOfBits n m p.1 p.2 == colourOfBits n m x y)

/-- Monochromatic `k`-clique count by *subset enumeration* — deliberately naive,
used to cross-check `monoCount`. -/
def subsetMonoCount (n k : Nat) (s : List Char) : Nat :=
  ((subsetsOfSize n k).filter (fun t => subsetMono n s t)).length

/-- Is the bitmask colouring free of monochromatic `k`-cliques? (subset version) -/
def cleanBits (n k m : Nat) : Bool :=
  (subsetsOfSize n k).all (fun t => !(subsetMonoBits n m t))

/-- The colouring masks below `bound` that are free of monochromatic `k`-cliques.
With `bound = 2^(n choose 2)` this is a finite data structure proving `R(k,k) > n`
when it is non-empty, and `R(k,k) <= n` when it is empty.  (Used empty, for
`n = 6, k = 3`.) -/
def cleanMasks (n k bound : Nat) : List Nat :=
  (List.range bound).filter (fun m => cleanBits n k m)

/-! ### Circulant (translation invariant) colourings -/

/-- Difference masks below `bound` whose circulant colouring is clean.  With
`bound = 2^(n/2)` this is the exhaustive statement of the
`certs/circulant/*.json` certificates: a non-empty list exhibits a witness
(`R(k,k) > n`), the empty list is the negative result that no circulant
colouring of `K n` avoids a monochromatic `K k`. -/
def cleanCirculantMasks (n k bound : Nat) : List Nat :=
  (List.range bound).filter (fun m => circulantClean n k m)

/-! ### Multicolour instances (one forbidden clique size per colour)

A multicolour colouring is a list with one digit per edge in the same
lexicographic order that `edgeIndex` uses, so the Python and the Lean verifier
share one decoding path.  Colour `c` is the `c`-th entry of `sizes`, and entry
`c` of `multiMonoCount` counts the monochromatic `sizes[c]`-cliques of colour `c`.
-/

/-- Colour of the edge `{u, v}` in a multicolour colouring (0 if out of range). -/
def edgeColour (n : Nat) (coloring : List Nat) (u v : Nat) : Nat :=
  coloring.getD (edgeIndex n (Nat.min u v) (Nat.max u v)) 0

/-- Adjacency mask of vertex `v` in colour `c` of a multicolour colouring. -/
def colourAdj (n : Nat) (coloring : List Nat) (c : Nat) : Nat → Nat :=
  fun v =>
    (List.range n).foldl
      (fun acc u =>
        if u == v then acc
        else if edgeColour n coloring u v == c then acc ||| (1 <<< u) else acc)
      0

/-- Monochromatic forbidden-clique counts of a multicolour colouring, one per
colour, by the bitmask recursion `countCliques`.

`multiMonoCount n [3, 3, 5] <colouring> = [0, 0, 0]` is the machine-checkable
content of a clean multicolour witness. -/
def multiMonoCountFrom (n : Nat) (coloring : List Nat) : Nat → List Nat → List Nat
  | _, [] => []
  | c, s :: rest =>
    countCliques n (colourAdj n coloring c) (fullMask n) s
      :: multiMonoCountFrom n coloring (c + 1) rest

/-- `multiMonoCount n sizes coloring`: exact violation counts, one per colour. -/
def multiMonoCount (n : Nat) (sizes : List Nat) (coloring : List Nat) : List Nat :=
  multiMonoCountFrom n coloring 0 sizes

/-- Does the subset `t` consist of edges that all carry colour `c`? -/
def monoSubsetColour (n c : Nat) (coloring : List Nat) (t : List Nat) : Bool :=
  (allPairs t).all (fun p => edgeColour n coloring p.1 p.2 == c)

/-- The same counts by *subset enumeration* — deliberately naive, and used to
cross-check `multiMonoCount` on the cases where the enumeration is cheap. -/
def multiSubsetMonoCountFrom (n : Nat) (coloring : List Nat) :
    Nat → List Nat → List Nat
  | _, [] => []
  | c, s :: rest =>
    ((subsetsOfSize n s).filter (monoSubsetColour n c coloring)).length
      :: multiSubsetMonoCountFrom n coloring (c + 1) rest

/-- `multiSubsetMonoCount n sizes coloring`, the naive cross-check. -/
def multiSubsetMonoCount (n : Nat) (sizes : List Nat) (coloring : List Nat) : List Nat :=
  multiSubsetMonoCountFrom n coloring 0 sizes

/-- The distinct edge-class sets that an `s`-clique of `K n` can use, sorted and
deduplicated — the constraint groups of the `circulant_multicolour` encoding.

Computed from the cliques themselves, so a certificate's claimed encoding size is
reproduced here instead of trusted. -/
def cliqueClassGroups (n s : Nat) : List (List Nat) :=
  let classesOf (vs : List Nat) : List Nat :=
    ((allPairs vs).map (fun p => diffClass n p.1 p.2)).mergeSort (fun a b => decide (a ≤ b))
  ((subsetsOfSize n s).map (fun vs => (classesOf vs).eraseDups)).eraseDups

/-! ### Cayley (translation invariant over a group) colourings

A Cayley colouring assigns a colour per *inversion class* `{d, d⁻¹}` of a group
of order `n`, so the colouring is translation invariant and the circulant
encoding is the special case where the group is `Z n`.  The group itself is data:
a certificate stores its multiplication table and its inverse list, because the
`n` labels are the vertices and a colouring is decided by `x⁻¹ · y`.

What is checked here is the same thing the Python verifier checks, in Lean: that
the stored table *is* a group, that the class and clique-group counts the encoding
size is computed from are reproduced from that table, and — for a witness — that
the expanded colouring has no monochromatic forbidden clique.
-/

/-- Row `i`, column `j` of a stored multiplication table (`0` out of range). -/
def entry (rows : List (List Nat)) (i j : Nat) : Nat :=
  (rows.getD i []).getD j 0

/-- The identity of a table: the row that fixes every element (`0` when there is
none, a case `isCayleyGroup` rejects). -/
def cayleyId (table : List (List Nat)) : Nat :=
  ((List.range table.length).find? (fun e =>
    (List.range table.length).all (fun y => entry table e y == y))).getD 0

/-- Is the stored table a group with the stored inverse list?

Closure and range are structural (`entry` is total), so the checks are: square
rows, an inverse list of the right length, a two-sided identity, a two-sided
inverse at every element, and associativity over every triple.  This is the
same test `cayley.verify_group` makes in Python, restated so the Lean kernel (or
`native_decide`) re-derives it from the certificate's own data. -/
def isCayleyGroup (table : List (List Nat)) (inv : List Nat) : Bool :=
  let n := table.length
  table.all (fun row => row.length == n)
    && (inv.length == n)
    && (let e := cayleyId table
        (List.range n).all (fun y => entry table e y == y && entry table y e == y)
          && (List.range n).all (fun x =>
               entry table x (inv.getD x n) == e && entry table (inv.getD x n) x == e)
          && (List.range n).all (fun a => (List.range n).all (fun b =>
               (List.range n).all (fun c =>
                 entry table (entry table a b) c == entry table a (entry table b c)))))

/-- An element of order three in the table: some `g ≠ 1` with `g³ = 1`.

Cauchy's theorem guarantees one whenever `3 ∣ n`, which is what makes the
`3 ∣ n` obstruction a statement about *every* group of that order rather than
about the cyclic one; here it is checked on the stored table. -/
def hasOrderThree (table : List (List Nat)) : Bool :=
  let e := cayleyId table
  (List.range table.length).any (fun g =>
    g != e && entry table (entry table g g) g == e)

/-- The inversion class of `d` in the labelling the certificates use: the smaller
of `d` and `d⁻¹` (so `d` and `d⁻¹` share one class, as they must). -/
def cayleyClass (inv : List Nat) (d : Nat) : Nat :=
  Nat.min d (inv.getD d d)

/-- The class of the difference `x⁻¹ · y`, which is what decides the colour of
the edge `{x, y}` of a Cayley colouring. -/
def cayleyDiff (table : List (List Nat)) (inv : List Nat) (x y : Nat) : Nat :=
  cayleyClass inv (entry table (inv.getD x x) y)

/-- The distinct inversion classes of the group (the identity excluded, matching
the encoder: one variable per class *and colour*). -/
def cayleyClasses (table : List (List Nat)) (inv : List Nat) : List Nat :=
  (((List.range table.length).filter (fun d => d != 0)).map (cayleyClass inv)).eraseDups

/-- The distinct class sets an `s`-clique can use, sorted and deduplicated —
the constraint groups of the Cayley encoding.

Computed from the table's own differences, exactly as `cliqueClassGroups` does
for `Z n`, so the encoding size of a certificate is reproduced here rather than
trusted.  (The encoder translates each clique to contain the identity, which
loses nothing because differences are invariant under translation; enumerating
every `s`-subset here gives the same collection of class sets.) -/
def cayleyCliqueClassGroups (table : List (List Nat)) (inv : List Nat) (s : Nat) :
    List (List Nat) :=
  let classesOf (vs : List Nat) : List Nat :=
    ((allPairs vs).map (fun p => cayleyDiff table inv p.1 p.2)).mergeSort
      (fun a b => decide (a ≤ b))
  ((subsetsOfSize table.length s).map (fun vs => (classesOf vs).eraseDups)).eraseDups

/-! ### Unit-distance drawings -/

/-- Are the stored edges unit length within `tol`, given coordinates scaled by
`S`?  The exact integer condition is `| |a-b|^2 - S^2 | <= tol`. -/
def unitEdges (S tol : Int) (pts : List (List Int)) (es : List (Nat × Nat)) : Bool :=
  es.all (fun e =>
    match pts[e.1]?, pts[e.2]? with
    | some a, some b => (normSq (sub a b) - S * S).natAbs ≤ tol.natAbs
    | _, _ => false)

/-- All `k`-colourings of `n` vertices, as lists of colours. -/
def colouringsOf (n k : Nat) : List (List Nat) :=
  (List.range n).foldl
    (fun acc _ => acc.flatMap (fun a => (List.range k).map (fun c => c :: a)))
    [[]]

/-- Is `col` a proper colouring of the stored edge list on `n` vertices? -/
def properColouring (n : Nat) (col : List Nat) (es : List (Nat × Nat)) : Bool :=
  es.all (fun e => e.1 < n && e.2 < n && (col.getD e.1 0) != (col.getD e.2 0))

/-- Does the graph admit a proper colouring with `k` colours?  Enumerates all
`k^n` colourings, so it is only used for the *lower* bound (`k = chi - 1`): the
upper bound comes from an explicit witness colouring instead, which keeps the
search small. -/
def colouringExists (n k : Nat) (es : List (Nat × Nat)) : Bool :=
  (colouringsOf n k).any (fun a => properColouring n a es)

/-- Exact chromatic number check with a witness: the explicit colouring `col` is
proper on the stored edges, and no proper `chi - 1`-colouring exists.  Together
that pins the chromatic number of the stored graph to `chi`. -/
def chromaticWitness (n chi : Nat) (col : List Nat) (es : List (Nat × Nat)) : Bool :=
  properColouring n col es && !colouringExists n (chi - 1) es
