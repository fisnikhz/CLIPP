# Adapted solver strategy for Street Cleaning

## Executive recommendation

Treat the problem as a **heterogeneous multi-vehicle directed arc-routing problem with required edges and optional profitable edges**. The strongest practical competition approach is:

1. directed shortest-path preprocessing;
2. mandatory-first regret insertion into compatible vehicle routes;
3. profitable optional-edge insertion using exact marginal score;
4. multi-start adaptive large-neighborhood search (ALNS), with simulated-annealing acceptance;
5. final route expansion and an independent validator/scorer.

This is a better fit than copying the reference repository's bounded depth-first walk. The repository contributes useful principles—global unique-edge accounting, favoring unvisited streets, reward/time ordering, sequential diversification, and a wall-clock search budget—but its implementation does not handle return-to-depot, mandatory streets, heterogeneous vehicles, cleaning decisions, or water cost.

### Balancing scores across datasets

When a shared compute budget or parameter set creates a trade-off between dataset
scores, compare portfolios lexicographically:

```text
(invalid_output_count,
 max_i(1-score_i),
 CVaR_worst_25%(1-score_i),
 mean_i(1-score_i))
```

Validity is a hard priority, followed by the weakest output, the weak tail, and
finally global average quality. For dashboards or parameter tuning, a scalar
approximation is:

```text
loss = 10 * invalid_count
     + 0.55 * max_error
     + 0.25 * worst_quartile_mean_error
     + 0.20 * mean_error
```

CVaR/worst-tail error is preferable to score variance. Variance can be reduced by
making a strong output worse, whereas worst-tail error only rewards improving weak
outputs. Since outputs for independent datasets do not consume one another's route
capacity, always retain each dataset's best known valid solution; use this portfolio
criterion primarily to allocate search time toward the current weakest dataset.

## 1. Mapping from Hash Code 2014

| Hash Code 2014 | Street Cleaning | Reusable? |
|---|---|---|
| Junction | Junction | Direct mapping |
| Street with direction, time, length | Street with the same fields plus category and requirement | Extend edge state |
| Street View car | Small/Medium/Large cleaning vehicle | Redesign for compatibility and waste |
| Traversing a street scores it | Explicitly cleaning an eligible street scores it | Redesign traversal state |
| Unique covered length | Unique cleaned length | Reuse global ownership/bitset idea |
| Common start | Common depot | Extend: every route must also return |
| Per-car time budget | Per-vehicle time budget | Reuse, with reserved return time |
| Maximize unique length | Maximize coverage and efficiency | Replace `length/time` by marginal utility/incremental time |
| Any street optional | Mandatory, optional, connector | Mandatory feasibility must be phase one |
| Homogeneous cars | Three capacities | Vehicle assignment is part of the optimization |

### What the reference code actually does

The Java solver in the supplied repository builds an adjacency list and searches each car sequentially with a recursive DFS. At every junction it sorts outgoing streets by:

1. increasing visit count; then
2. decreasing `length / traversal_time`.

It initializes visit counts with routes selected for earlier cars, doubles a street's visit marker during recursion to discourage repeated use, retains the longest route seen, and stops each car's search after a fixed wall-clock budget. This is a lightweight randomized/ordered lookahead strategy, not an Euler-tour, beam-search, simulated-annealing, or genetic solver.

Reusable ideas:

- Maintain one global owner/cleaned state, so two vehicles do not claim the same reward.
- Prefer new profitable work over deadheading.
- Rank choices by marginal value per added second.
- Put an explicit wall-clock limit around improvement.
- Generate multiple different solutions by changing ordering/tie-breaking.

Ideas that must not be copied unchanged:

- Recursive enumeration can explode with branching factor and does not scale to `M = 100,000`.
- The original code does not reserve time to return to the depot.
- It treats traversal as service; this problem separates traversal from cleaning.
- It has no hard feasibility phase for mandatory streets.
- It has no vehicle compatibility or assignment-dependent waste.
- Its raw length total is not this problem's objective.
- Sequentially finalizing one vehicle too early can consume streets or time needed by a scarce vehicle type.

## 2. Mathematical objective

Let cleanable street `e` have length `l[e]` meters, requirement `r[e]` in `{10,20,30}`, and category `cat[e]`. Vehicle `v` has capacity `p[v]` in `{10,20,30}`.

Define binary `x[e,v] = 1` when vehicle `v` cleans street `e`. Then:

```text
cleaned_length = sum(e,v) x[e,v] * l[e]
waste          = sum(e,v) x[e,v] * (p[v] - r[e]) * l[e] / 1000
```

The exact objective is:

```text
maximize  alpha * cleaned_length / Lmax
        + (1-alpha) * (1 - waste / Wmax)
```

subject to:

- `sum(v) x[e,v] = 1` for every mandatory edge;
- `sum(v) x[e,v] <= 1` for every optional edge;
- `x[e,v] = 0` if `p[v] < r[e]`;
- every vehicle route is a direction-respecting depot-to-depot walk;
- cleaned edge `e` occurs in the cleaning vehicle's walk in a valid orientation;
- each route's traversal time is at most `T`.

Ignoring the constant `(1-alpha)`, the exact additive contribution of assigning edge `e` to vehicle `v` is:

```text
q(e,v) = alpha * l[e] / Lmax
       - (1-alpha) * ((p[v]-r[e]) * l[e] / 1000) / Wmax
```

This is the correct replacement for the reference solver's `length/time`. For optional work, `q(e,v)` can be negative; such an edge should normally not be cleaned. Mandatory edges must be assigned even when their contribution is negative.

For insertion with added route time `delta_t`, use:

```text
optional_density = q(e,v) / max(1, delta_t)
mandatory_merit  = -delta_t - lambda_w * normalized_waste(e,v)
```

Use lexicographic comparison while constructing feasibility:

```text
(mandatory edges missing, total overtime, incompatibility count,
 negative exact score)
```

Only after the first three fields are zero should the official score decide between solutions.

### Important scoring observations

- The statement's claim that the optimal strategy cleans as many optional streets as possible is false for the stated weighted score. Cleaning a positive-waste optional edge can reduce the score.
- If `Wmax = 0` (for example, all cleanable streets require 30), the formula divides by zero. Define `Efficiency = 1` when `Wmax = 0`, or revise the specification.
- Zero-waste optional edges always have nonnegative marginal score, but may still displace more valuable work because route time is limited.

## 3. Correct baseline

No algorithm can promise a valid output for every syntactically valid input unless the statement guarantees that mandatory streets are jointly feasible. The baseline should always emit a well-formed output and either produce a valid solution or explicitly report that no mandatory-feasible solution was found.

### Baseline A: minimal safe output

Give every vehicle route `[S]` and an empty cleaning list. This is valid only when there are no mandatory streets. It is still useful for testing the parser, writer, and validator.

### Baseline B: mandatory-first cheapest insertion

Represent each route as an ordered list of **service tasks**, not every traversed arc. A service task is `(edge_id, orientation, clean=true)`. Shortest paths between consecutive service tasks are deadhead travel and are expanded only when writing the answer.

1. Initialize all vehicle routes as depot-to-depot cycles with time zero.
2. Reject immediately if a mandatory requirement has no compatible vehicle type.
3. For every mandatory edge, determine compatible vehicles and both legal orientations.
4. Sort mandatory edges by difficulty:
   - heavy before medium before light;
   - fewer compatible vehicles first;
   - larger minimum depot round-trip time first;
   - larger regret between best and second-best insertion first.
5. Insert each mandatory edge at the feasible route position with minimum added travel time, breaking ties by lower water waste.
6. If no insertion fits, try relocating one or two already inserted tasks; if that fails, restart with randomized tie-breaking.
7. After mandatory feasibility, repeatedly insert the optional `(edge, vehicle, position, orientation)` with largest positive `q/delta_t` while it fits.
8. Expand task sequences with shortest paths, return to the depot, and validate from scratch.

The insertion delta between predecessor task endpoint `a` and successor task start `b` is:

```text
delta_t = dist(a, tail(e)) + time[e] + dist(head(e), b) - dist(a,b)
```

Evaluate both orientations for a two-way edge. A one-way edge has only `A -> B`.

This baseline is simple, score-aware, and valid whenever all insertions succeed. Its weakness is myopia: an early cheap insertion may block a later scarce or geographically isolated mandatory edge.

## 4. Advanced strategy: multi-start ALNS

ALNS is a better primary improvement method than a genetic algorithm here. Routes have hard feasibility, task ownership, orientation, and type compatibility; destroy/repair operations preserve and exploit that structure. Genetic crossover tends to create duplicates, missing mandatory work, and broken routes that require expensive repair.

### Phase 1: preprocess feasibility

- Build forward and reverse adjacency arrays.
- Run Dijkstra from the depot on the forward graph: `dist_from_depot`.
- Run Dijkstra from the depot on the reversed graph: `dist_to_depot[u] = dist(u,S)`.
- Mark an edge impossible if no compatible vehicle exists, its legal orientation cannot be reached from the depot, or it cannot return to the depot.
- For every traversal from current node `u` to `w`, enforce:

```text
time_used + traversal_time(u,w) + dist_to_depot[w] <= T
```

This single condition safely adapts the reference walk heuristic to the return requirement.

Do not compute an `N x N` distance matrix. At `N = 10,000` it may be marginal in raw distance storage but predecessor/path storage and repeated construction costs become wasteful. Use lazy Dijkstra caches from task endpoints actually queried, bounded with LRU eviction. Store only distances to candidate task endpoints where possible; rerun Dijkstra to reconstruct final connector paths.

Coordinates may rank nearby candidates, but they are not a safe shortest-time bound unless the input guarantees a relation between geometry and traversal time.

### Phase 2: randomized regret construction

For each unassigned mandatory edge, compute its best and second-best feasible insertion costs over a filtered set of vehicle/position candidates.

```text
regret(e) = second_best_cost(e) - best_cost(e)
```

Choose from a restricted candidate list containing the highest-regret edges. Select randomly with bias toward the top. This protects tasks with only one good placement while producing different seeds.

After all mandatory edges are assigned, insert positive-utility optional edges by `q/delta_t`. Use a restricted candidate list rather than always taking the maximum.

### Phase 3: local neighborhoods

Apply these moves, roughly in this order:

1. **Orientation flip:** reverse a two-way service edge and reconnect neighbors.
2. **Relocate:** move one service edge within a route or to another compatible vehicle.
3. **Swap:** exchange two service edges between routes, respecting capacity.
4. **2-opt-like segment reconnection:** useful only after checking directed reachability; ordinary undirected 2-opt is not automatically valid.
5. **Optional insertion/removal:** insert positive-value work; remove an optional edge whose route-time opportunity cost is too high.
6. **Type reassignment:** move light work from a large vehicle to a small/medium one to reduce waste, if connector time permits.
7. **Chain move:** relocate two or three geographically related edges together.

Maintain exact route time and exact objective deltas. Reject any move that misses a mandatory edge, duplicates ownership, violates compatibility, breaks directed reachability, or exceeds `T`—except inside an explicitly penalized repair phase.

### Phase 4: ALNS destroy and repair

Destroy 5–20% of assigned tasks using one of:

- random removal;
- worst insertion-cost removal;
- related removal (nearby endpoints, same requirement, or same vehicle);
- route-segment removal;
- water-waste removal;
- scarce-vehicle cleanup, removing low-requirement work from large vehicles.

Repair mandatory tasks first with regret-2 or regret-3 insertion, then repair optional tasks only when their marginal contribution is positive. Track each operator's recent improvement rate and raise the selection weight of successful operators.

Accept improvements immediately. Accept a worse feasible solution with simulated annealing probability:

```text
P(accept) = exp((score_new - score_current) / temperature)
```

Cool temperature over the wall-clock budget and always retain the global best feasible solution. Reheat or restart after a long stagnation period.

### Optional beam-search adaptation of the repository DFS

For a fast second-stage route filler, replace recursive DFS with a bounded beam. A state contains current node, used time, owned-cleaned bitset delta, and a guaranteed return bound. Expand only candidate outgoing arcs plus shortest-path steps toward promising unassigned tasks. Rank by:

```text
accumulated_exact_gain
+ beta * estimated_future_gain
- gamma * repeated_travel_time
- huge_penalty * return_infeasibility
```

Keep only the best `B` states per depth. This preserves the reference implementation's lookahead flavor without exponential unbounded recursion. Use it as a route-filling heuristic, not as the main mandatory assignment engine.

## 5. Data structures

Use compact arrays; `M = 100,000` makes object-heavy graph representations unnecessarily costly.

```text
Edge:
  a, b, direction, time, length, category, requirement

Arc:
  to, edge_id, next_index              // forward-star adjacency

Vehicle:
  capacity, route_id

ServiceTask:
  edge_id, reversed, vehicle_id

Route:
  dynamic array / linked-index sequence of ServiceTask
  total_time, exact_score_contribution
  prefix/suffix timing caches if needed

Global solution:
  owner[edge_id] = -1 or vehicle_id
  cleaned bitset
  mandatory_missing
  total_cleaned_length
  total_waste
```

Recommended implementation details:

- binary heap for Dijkstra;
- `long` for route time sums, lengths, and scaled waste;
- doubles only for final normalized score and SA probability;
- fixed-point integer utility for stable comparisons if desired;
- versioned arrays for Dijkstra visitation, avoiding `O(N)` clearing each run;
- lazy shortest-path cache keyed by source junction;
- per-route candidate positions indexed by endpoint proximity;
- immutable parsed instance and mutable solution state;
- independent validator/scorer that never trusts cached deltas.

## 6. End-to-end pseudocode

```text
solve(instance, wall_clock_limit):
    graph = build_directed_arcs(instance)
    dist_from_S = dijkstra(graph, S)
    dist_to_S   = dijkstra(reverse(graph), S)
    validate_instance_and_find_impossible_mandatory_edges()

    best = NONE
    while time_remaining():
        solution = empty_routes()

        mandatory = all_mandatory_edges()
        while mandatory not empty:
            candidates = []
            for e in filtered_high_difficulty_subset(mandatory):
                best2 = two_best_compatible_insertions(e, solution)
                candidates.push(e, regret(best2), best2.best)

            e = randomized_choice(top_regret_candidates)
            if no feasible insertion for e:
                solution = mandatory_repair_or_restart(solution, e)
                if repair failed: restart
            apply(best insertion for e)
            remove e from mandatory

        optional_heap = build_positive_optional_insertions(solution)
        while optional_heap not empty:
            move = pop_best_validated_q_over_delta_time(optional_heap)
            if move is stale: recompute and reinsert
            else if move.q > 0 and move fits: apply(move)

        solution = local_search(solution)
        solution = ALNS_with_SA(solution, remaining_slice)

        expanded = expand_connectors_with_shortest_paths(solution)
        if independent_validate(expanded):
            best = max_by_official_score(best, expanded)

    return best or explicit_no_feasible_solution_result
```

### Incremental comparison

For two feasible solutions, compare official scores. Since the constant efficiency term is the same, it is enough to compare:

```text
alpha * cleaned_length / Lmax - (1-alpha) * waste / Wmax
```

For partial or temporarily infeasible solutions, compare lexicographically or use a penalty:

```text
search_value = exact_additive_score
             - Pm * mandatory_missing
             - Pt * total_overtime / T
             - Pc * incompatible_assignments
             - Pd * duplicate_cleanings
```

Choose `Pm` larger than the largest possible score range. Adaptive penalties are useful in ALNS, but the stored global best must always be fully valid.

## 7. Complexity and bottlenecks

Let `A <= 2M` be the number of directed arcs and `K` the number of distinct Dijkstra source endpoints actually cached.

- Graph storage: `O(N + M)` memory.
- Depot forward/reverse preprocessing: `O((N + A) log N)` time.
- Lazy distance queries: up to `O(K (N + A) log N)` worst case; this is the main bottleneck.
- Naive insertion evaluation: `O(tasks * vehicles * route_positions)`, too slow at full scale.
- Filtered insertion with `k` candidate positions/vehicles: approximately `O(tasks * k)` distance lookups per repair pass.
- Route expansion: one shortest-path query per consecutive pair of service tasks, with cache reuse.

Control the bottlenecks by:

- considering only compatible vehicles;
- filtering positions using endpoint proximity and route neighborhoods;
- lazy invalidation in optional priority queues;
- caching route deltas and recomputing only affected neighbors;
- limiting destroy size and ALNS repair candidates;
- rerunning exact shortest paths only for shortlisted moves;
- using multiple short restarts instead of one enormous local optimum search.

## 8. Edge cases

- **Disconnected/directed-unreachable graph:** mandatory edges must be reachable from and able to return to the depot in a legal service orientation. Otherwise the instance is infeasible.
- **Insufficient vehicle types:** a heavy mandatory edge with no large vehicle is infeasible; similarly account for route-time capacity across all compatible vehicles.
- **Tight time limits:** reject an expansion unless current time plus the move plus `dist_to_depot` fits. Do not postpone the return check.
- **Duplicate traversal:** allowed and often necessary; it earns no extra coverage. Mark only one vehicle as cleaner/owner.
- **Duplicate cleaning:** never generate it. The statement is internally inconsistent about whether it is allowed and how its waste is counted.
- **One-way service:** clean only while traversing the legal arc.
- **Two-way service:** evaluate both orientations; clean once.
- **Zero-length cleanable street:** no coverage and no waste; clean it only if mandatory.
- **`alpha = 1`:** ignore waste in score but retain capacity compatibility.
- **`alpha = 0`:** optional positive-waste cleaning is harmful; zero-waste optional cleaning is score-neutral. Mandatory coverage is still a hard constraint.
- **`Wmax = 0`:** require a scoring convention; recommended efficiency is 1.
- **Many vehicles:** idle vehicles should output `[S]`; route construction should not force every vehicle to move.
- **Greedy trap:** regret insertion, relocation repair, ALNS removal, and multi-start directly address early blocking decisions.

## 9. Implementation roadmap

Keep the solver modular but small:

```text
InstanceParser
  parse(path) -> Instance

Graph
  build_arcs()
  dijkstra(source, reversed=false)
  shortest_path(source, target)

ScoreModel
  edge_gain(edge, vehicle)
  official_score(solution)
  search_value(solution)

Solution / Route
  owner[], service task sequences, cached time/score
  apply/undo insertion, removal, relocate, swap

Constructor
  mandatory_regret_insert()
  optional_profit_insert()

Improver
  local_search()
  destroy()
  repair()
  annealing_loop()

Expander
  service_routes -> explicit junction walks and cleaned edge lists

Validator
  parse output independently
  check directions, times, depot, capacity, ownership, mandatory coverage
  recompute score

Writer
  emit exact submission format
```

Implementation order:

1. Parser, graph, output writer, validator/scorer.
2. Reverse-Dijkstra return bounds and mandatory feasibility diagnostics.
3. Mandatory cheapest insertion and optional positive-gain insertion.
4. Randomized regret insertion and multi-start.
5. Relocate/swap/orientation/optional moves.
6. ALNS destroy-repair with SA acceptance.
7. Profiling, bounded distance cache, candidate filtering, and parameter tuning.

Always test an emitted solution by reading it back through the independent validator.

## 10. Approach ranking

1. **Cheapest compatible mandatory insertion + profitable optional insertion** — simplest credible baseline; implement first.
2. **Randomized regret insertion + multi-start + local relocate/swap** — best score/engineering ratio; implement second.
3. **ALNS with SA acceptance and adaptive destroy/repair operators** — strongest recommended competition approach; implement third.
4. **Bounded beam route filler** — useful supplementary exploitation of the reference repository's lookahead idea.
5. **Genetic algorithm** — lowest recommendation because feasibility-preserving crossover is complex and ALNS offers more controlled improvement.

The practical sweet spot is option 3 built incrementally on options 1 and 2. It directly optimizes this problem's additive coverage/waste utility, protects mandatory feasibility, reserves return time, and can exploit every extra second of competition runtime.

## Specification issues to resolve before coding

The current document contains several contradictions that affect implementation:

1. The example input omits the promised `N` coordinate lines.
2. The example output route counts should be 5, 6, and 9, but are shown as 4, 5, and 8.
3. “Each street needs to be cleaned at most once” conflicts with text saying duplicate cleaning is accepted and incurs waste twice.
4. The scoring definition says waste is summed “over all cleaned streets,” which could mean unique streets, while another paragraph says duplicate cleaners waste water twice.
5. `Wmax` may be zero, with no division-by-zero convention.
6. There is no guarantee that all mandatory edges admit any feasible set of depot-returning routes.
7. The claim that cleaning more optional streets is always optimal conflicts with the weighted objective when optional cleaning has positive waste.

Resolve these in the judge and statement first; otherwise a solver and judge can legitimately disagree.

## References

- [Reference repository](https://github.com/ivanmakhnyk/StreetViewRouting-HashCode)
- [Official Hash Code 2014 Street View Routing statement](https://storage.googleapis.com/coding-competitions.appspot.com/HC/2014/hashcode2014_final_task.pdf)
