#############################################################################
##
##  gap_export_smallgroups.g     export one order of the SmallGroups library
##
##  Writes one JSON object per line, after a header line:
##
##      {"gap":"4.15.1","order":128,"n":2328}
##      {"order":128,"id":1,"degree":8,"generators":[[0,1,...],...],
##       "orders":{"1":1,"2":5,...},"classes":{"1:1":1,"2:8":3,...},
##       "center":128,"derived":1,"exponent":2,"abelian":true}
##
##  `generators` are the images of 0..degree-1 under a faithful permutation
##  representation of SmallGroup(order, id), i.e. exactly what `oplab.cayley`'s
##  `permutation` family rebuilds the multiplication table from.  Nothing
##  downstream trusts this file: the Python side closes these permutations and
##  checks that the result has the declared order, then recomputes the invariants
##  below (`orders`, `classes` — the conjugacy-class structure, by element order
##  and class size — `center`, `derived`, `exponent`, `abelian`) from the rebuilt
##  table and refuses the row if they disagree.  A line that is corrupt, unfaithful
##  or mislabelled therefore fails loudly instead of producing a theorem about the
##  wrong group.
##
##  The `id` is provenance — which entry of the library this is — and
##  `StructureDescription` is deliberately not called: it can be slow on
##  p-groups and it is not a number any claim here rests on.
##
##  Usage (the variables are the interface; `first_id`/`last_id` are optional and bound
##  the id range, for splitting a long export over several processes):
##
##      gap -q -b -c 'order := 128;; out := "/tmp/smallgroups_128.jsonl"; \
##                    Read("scripts/gap_export_smallgroups.g"); QUIT;'
##
##  then  python scripts/portfolio_build.py --jsonl /tmp/smallgroups_128.jsonl \
##        --out data/smallgroups_128.json
##
##  The ranges are concatenated in id order (one header, the rows sorted by id)
##  before the builder is run; `make portfolio` is the four-way split used for
##  order 128, whose 2328 groups take about half an hour in one process.
##
#############################################################################

if not IsBound(order) or not IsBound(out) then
  Error("set `order` and `out` before Read()ing this file");
fi;
if not IsBound(progress) then
  progress := 200;
fi;
n := NrSmallGroups(order);
# an export can be split over several processes (one range each), which is how the
# 2328 groups of order 128 are produced: the ranges are concatenated in id order
# afterwards, and the header line of each part says which range it is
if not IsBound(first_id) then
  first_id := 1;
fi;
if not IsBound(last_id) then
  last_id := n;
fi;
stream := OutputTextFile(out, false);
SetPrintFormattingStatus(stream, false);

PrintTo(stream, "{\"gap\": \"", GAPInfo.Version, "\", \"order\": ", order,
        ", \"n\": ", n, ", \"first_id\": ", first_id, ", \"last_id\": ", last_id, "}\n");

for id in [first_id .. last_id] do
  G := SmallGroup(order, id);
  P := Image(IsomorphismPermGroup(G));
  gens := GeneratorsOfGroup(P);
  degree := LargestMovedPoint(P);
  if degree = 0 then
    degree := 1;
  fi;
  profile := Collected(List(Elements(G), Order));
  class_profile := Collected(List(ConjugacyClasses(G),
                                  c -> [Order(Representative(c)), Size(c)]));

  PrintTo(stream, "{\"order\": ", order, ", \"id\": ", id);
  PrintTo(stream, ", \"degree\": ", degree, ", \"generators\": [");
  for i in [1 .. Length(gens)] do
    images := [];
    for x in [1 .. degree] do
      Add(images, (x ^ gens[i]) - 1);
    od;
    if i > 1 then
      PrintTo(stream, ", ");
    fi;
    PrintTo(stream, images);
  od;
  PrintTo(stream, "], \"orders\": {");
  for i in [1 .. Length(profile)] do
    if i > 1 then
      PrintTo(stream, ", ");
    fi;
    PrintTo(stream, "\"", profile[i][1], "\": ", profile[i][2]);
  od;
  PrintTo(stream, "}, \"classes\": {");
  for i in [1 .. Length(class_profile)] do
    if i > 1 then
      PrintTo(stream, ", ");
    fi;
    PrintTo(stream, "\"", class_profile[i][1][1], ":", class_profile[i][1][2],
            "\": ", class_profile[i][2]);
  od;
  PrintTo(stream, "}, \"center\": ", Size(Center(G)));
  PrintTo(stream, ", \"derived\": ", Size(DerivedSubgroup(G)));
  PrintTo(stream, ", \"exponent\": ", Exponent(G));
  PrintTo(stream, ", \"abelian\": ", IsAbelian(G), "}\n");

  if id mod progress = 0 then
    Print("# ", id, " of ", last_id, "\n");
  fi;
od;

CloseStream(stream);
Print("# done: ", last_id - first_id + 1, " groups of order ", order, " (", first_id, "..", last_id,
      ") -> ", out, "\n");
QUIT;
