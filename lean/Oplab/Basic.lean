/-
  Shared definitions for the Lean layer of open-problems-lab.

  Everything here is deliberately dependency-free (no Mathlib): the claims are
  finite computations, so plain definitions plus `decide` (kernel-checked
  evaluation) or `native_decide` (compiled evaluation) are enough, and the
  project builds in seconds.
-/

set_option maxRecDepth 1000000

/-! ### Spherical configurations (integers only) -/

/-- All pairs `(x, y)` with `x` strictly before `y` in a list. -/
def allPairs {α : Type} (l : List α) : List (α × α) :=
  match l with
  | [] => []
  | x :: xs => xs.map (fun y => (x, y)) ++ allPairs xs

/-- Integer dot product of two vectors. -/
def dot (u v : List Int) : Int :=
  (u.zip v).foldl (fun acc p => acc + p.1 * p.2) 0

/-- Largest pairwise dot product over a list of vectors (0 for fewer than two). -/
def maxDot (vs : List (List Int)) : Int :=
  (allPairs vs).foldl (fun acc p => max acc (dot p.1 p.2)) 0

/-- Every vector of the list has squared norm `q`. -/
def normsAre (vs : List (List Int)) (q : Int) : Bool :=
  vs.all (fun v => dot v v == q)

/-! ### Ramsey colourings

Colourings are handled as bitmasks and strings rather than as `Fin n → Fin n →
Bool` functions: the certificates store a string of `n*(n-1)/2` characters, and
the checkers in `Oplab.Check` decode that string directly (see `colourOfChar`),
so there is a single decoding path shared by the Lean and the Python verifier.
-/

/-- Index of the edge `{u, v}` (`u < v`) in the lexicographic order used by the
Python certificates. -/
def edgeIndex (n u v : Nat) : Nat :=
  u * (2 * n - u - 1) / 2 + (v - u - 1)

/-! ### Vertex-transitive (circulant) colourings

A circulant colouring of `K n` is given by a difference set: bit `i` of `mask`
selects the difference `i + 1` and, with it, `n - (i + 1)`.  Translation
invariance then means a monochromatic clique exists anywhere iff one exists
through vertex 0, which is what makes the exhaustive statements below finite and
small. -/

/-- Number of free differences of `Z n`. -/
def freeDiffs (n : Nat) : Nat := n / 2

/-- Difference mask of the circulant colouring encoded by `mask`. -/
def diffMask (n mask : Nat) : Nat :=
  (List.range (freeDiffs n)).foldl
    (fun acc i =>
      if mask.testBit i then acc ||| (1 <<< (i + 1)) ||| (1 <<< (n - (i + 1))) else acc)
    0

/-- Adjacency mask of vertex `v` in the circulant graph. -/
def rotMask (n base v : Nat) : Nat :=
  ((base <<< v) ||| (base >>> (n - v))) &&& ((1 <<< n) - 1)

/-- Does the graph on `n` vertices with adjacency masks `adj` contain a `k`-clique
inside `mask`?  Pure bit recursion, with no loop over vertex indices: the top
vertex `v` of the candidate clique is the highest bit of `mask`, and either it is
used (remainder searched in `adj v` restricted to lower vertices, with `k - 1`)
or skipped (remainder searched in `mask` without `v`, same `k`).

`fuel` makes the recursion structural.  Any path of the search uses at most `k`
"use" steps and, between two of them, at most `popcount mask <= n` "skip" steps,
so `n * (k + 1) + 1` fuel is always enough; `hasClique` passes exactly that. -/
def hasCliqueFuel (fuel : Nat) (adj : Nat → Nat) (mask k : Nat) : Bool :=
  match fuel with
  | 0 => false
  | f + 1 =>
    if k == 0 then true
    else if mask == 0 then false
    else
      let v := mask.log2
      let below := mask &&& ((1 <<< v) - 1)
      hasCliqueFuel f adj (adj v &&& below) (k - 1)
        || hasCliqueFuel f adj below k

/-- `hasClique n adj mask k`: is there a `k`-clique of `adj` inside `mask`?
(`n` is only used to size the fuel.) -/
def hasClique (n : Nat) (adj : Nat → Nat) (mask k : Nat) : Bool :=
  hasCliqueFuel (n * (k + 1) + 1) adj mask k

/-- Blue adjacency mask of vertex `v` in a circulant colouring. -/
def blueMask (n base v : Nat) : Nat :=
  let full := (1 <<< n) - 1
  (full ^^^ rotMask n base v) &&& (full ^^^ (1 <<< v))

/-! ### The circulant class of an edge

`diffClass` is the invariant that makes the *circulant* sub-family of a
multicolour instance small: an edge of `Z n` is classified by `min(d, n - d)`,
and a colouring is circulant when it is constant on each class.  The multicolour
counters themselves live in `Oplab.Check`, next to the two-colour ones.

For `3 ∣ n` the three edges of `{0, n/3, 2n/3}` are all class `n / 3`: the class
`n / 3` carries one colour, and that colour is then monochromatic on those
`n / 3` triangles.  That is the arithmetic obstruction of every all-triangle
instance at a size divisible by three, proved per instance by `decide` on
`diffClass` and needing no solver. -/

/-- Difference class of the edge `{u, v}` of `Z n`: `min(d, n - d)`, `d = (v - u) mod n`. -/
def diffClass (n u v : Nat) : Nat :=
  Nat.min ((v + n - u) % n) (n - ((v + n - u) % n))

/-- Does the circulant colouring `mask` avoid every monochromatic `K k`?

Only cliques through vertex 0 need to be tested, because the colouring is
translation invariant; the neighbourhood of 0 is the difference mask itself. -/
def circulantClean (n k mask : Nat) : Bool :=
  let base := diffMask n mask
  let red := fun v => rotMask n base v
  let blue := fun v => blueMask n base v
  !(hasClique n red base (k - 1)) && !(hasClique n blue (blue 0) (k - 1))
