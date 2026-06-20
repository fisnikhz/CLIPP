# Mathematical analysis of `train_a`

## Target

`alpha = 1`, so the official score is exactly coverage:

```text
score = cleaned_length / 287611
```

To score above `0.90`, a solution must clean more than:

```text
0.90 * 287611 = 258849.9 meters
```

All mandatory streets contribute `117988` meters, so at least `140862` optional
meters are required.

## Fleet service-time capacity

The fleet has one Small, three Medium, and two Large vehicles. Ignoring all travel
between streets and all depot-return cost gives these aggregate capacities:

```text
Small:   1 * 28800 = 28800 seconds
Medium:  3 * 28800 = 86400 seconds
Large:   2 * 28800 = 57600 seconds
```

Mandatory service time by requirement is:

```text
Light:  12668 seconds
Medium: 22371 seconds
Heavy:  37759 seconds
```

After mandatory service, the optimistic residual capacities are therefore:

```text
Small:  16132 seconds
Medium: 64029 seconds
Large:  19841 seconds
```

All optional Light and Medium service can fit into the optimistic nested capacity
pools. Heavy optional work is restricted to the remaining `19841` Large-vehicle
seconds.

## Fractional upper bound

To make the bound as generous as possible, allow fractional cleaning of heavy
optional streets and select them by length/service-time ratio. The relaxation takes:

```text
edge 41: 100.0%
edge 45: 100.0%
edge 33: 100.0%
edge 64: 100.0%
edge 59: 100.0%
edge 78: 100.0%
edge 65: 100.0%
edge 21:  93.4%
```

This produces the following impossible-world upper bound:

```text
mandatory length                 = 117988
all Light/Medium optional length =  88704
fractional Heavy optional length =  54128.975
upper-bound length               = 260820.975
upper-bound score                = 0.906853
```

This is a valid upper bound because it ignores every real routing cost and permits
fractional streets. The margin between `0.90` and the relaxation is only:

```text
260820.975 - 258849.9 = 1971.075 meters
```

Therefore a score above `0.90` would require all direction constraints, depot
returns, connector travel, route fragmentation, and indivisible-edge packing to
lose less than 1,972 meters relative to a zero-travel fractional relaxation. The
actual graph necessarily incurs substantial routing overhead, making the requested
target almost certainly infeasible.

## Current solution gap

The current validated solution scores `0.693718` and cleans `199521` meters. Its
routes use `166692` of `172800` seconds. Approximately `51019` seconds are traversal
time not attributable to the explicitly cleaned service edges. This is the main
optimization gap.

The engineering target should be staged and evidence-driven:

1. reduce mandatory-route overhead;
2. use multi-edge destroy/repair to replace weak optional clusters;
3. compute a tighter integer upper bound or proof with a dedicated MIP/CP-SAT model;
4. stop using `0.90` as a required threshold unless that tighter model establishes
   feasibility.

