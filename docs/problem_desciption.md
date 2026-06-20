# Street Cleaning

## Introduction

Street cleaning is a logistics challenge: vehicles must be routed across a city, time is limited, and resources must be used wisely. Water is one of those resources — using more than necessary does not make a street cleaner, it simply wastes it.

In this problem, you will plan routes for a fleet of cleaning vehicles. Different streets need different amounts of water to be cleaned, and different vehicles carry different amounts. Your goal is to clean as many streets as possible while wasting as little water as possible — all within a fixed time budget.

## Task

Given a description of a city's streets, a fleet of cleaning vehicles, and a time limit, schedule the routes of all vehicles to maximize the total length of streets cleaned while minimizing water wasted, ensuring that all mandatory streets are cleaned and every vehicle returns to the depot on time.

## Problem Description

### City

The city is represented as a graph. The nodes represent junctions and the edges represent streets. The graph is a realistic but idealized representation of a city.

### Streets

There are **M** streets in the city with indices from `0` to `M–1`. Each street connects two junctions and has the following properties:

- **Direction** — each street is either one-way (traversable only from junction A towards junction B) or two-way (traversable in both directions).
- **Traversal time** — the time in seconds a vehicle takes to travel along the street.
- **Length** — the physical length of the street in meters. This is the value that contributes to the score when the street is cleaned.
- **Category** — one of three types: Mandatory, Optional, or Connector.
- **Cleaning requirement** — the minimum water needed per kilometer to clean the street (applicable to Mandatory and Optional streets only).

Each pair of junctions is connected by at most one street. Each street connects two different junctions.

### Street Categories

Every street belongs to exactly one of three categories:

| Category | Description |
|---|---|
| **Mandatory (M)** | Must be cleaned. A solution that fails to clean all mandatory streets is invalid. |
| **Optional (O)** | May be cleaned for additional score. These contribute to the objective but are not required. |
| **Connector (C)** | Used only for movement between junctions. Cleaning is not performed on connector streets, and they do not contribute to the score. |

### Cleaning Requirements

Every mandatory and optional street has a cleaning requirement level indicating the minimum amount of water needed per kilometer to clean it:

| Requirement Level | Description |
|---|---|
| **Light** — 10 liters/km | Residential or low-traffic streets |
| **Medium** — 20 liters/km | Standard urban streets |
| **Heavy** — 30 liters/km | High-traffic or industrial streets |

Connector streets have no cleaning requirement.

### Vehicles

The fleet consists of **C** vehicles of three possible types. Each vehicle type has a water capacity that determines which streets it can clean and how much water it uses:

| Type | Can Clean | Water Spent When Cleaning |
|---|---|---|
| **Small (S)** | Light streets only | 10 liters/km |
| **Medium (M)** | Light and Medium streets | 20 liters/km |
| **Large (L)** | Light, Medium, and Heavy streets | 30 liters/km |

A vehicle always spends water at its full capacity per kilometer when cleaning a street, regardless of the street's minimum requirement. For example, a Large vehicle cleaning a Light street spends 30 liters/km even though only 10 liters/km is required — wasting 20 liters/km.

Vehicles do not consume water when simply traversing a street without cleaning it (including all movement on connector streets).

**Water supply:** Vehicles have an unlimited water supply. Water waste is a cost metric penalized in the objective function, not a hard constraint — vehicles will never run out of water mid-route.

> **Note:** A vehicle can only clean a street if its capacity meets or exceeds the street's cleaning requirement. However, any vehicle may traverse any street (mandatory, optional, or connector) without cleaning it, at no water cost, as long as the direction allows.

### Speed

All vehicles travel at the same speed. Traversal time is a fixed property of each street and does not depend on the vehicle type. Every vehicle takes exactly the same amount of time to travel a given street.

### Depot

All vehicles start at and must return to a single junction designated as the depot (**S**).

### Time

All vehicles share the same time limit **T** (in seconds). Each vehicle's total route duration — the sum of traversal times of all streets in its path — must not exceed **T**.

### Cleaning

When a vehicle traverses a mandatory or optional street, it may choose to clean that street (provided its capacity is sufficient) or simply traverse it without cleaning. Each street needs to be cleaned at most once. If multiple vehicles traverse the same street, only one should clean it.

**Example.** Suppose a Large vehicle (30 L/km) traverses a Light optional street (requirement: 10 L/km, length: 200 m). If it cleans the street, it spends 30 × 0.2 = 6 liters. The street only needed 10 × 0.2 = 2 liters. The water waste is (30 – 10) × 0.2 = 4 liters. If instead a Small vehicle had cleaned this street, it would have spent exactly 2 liters with zero waste.

### Key Cleaning Rules

- **Capacity matching:** A vehicle can only clean a street if its water capacity is equal to or greater than the street's cleaning requirement. For example, a Small vehicle (10 L/km) cannot clean a Medium street (requirement: 20 L/km). It may still traverse the street without cleaning it.
- **Traversal vs. cleaning:** Any vehicle can traverse any street without cleaning it, at no water cost, as long as the street's direction allows. This is useful for repositioning between tasks.
- **Single-pass scoring:** Each street is scored at most once, regardless of how many vehicles clean it. If two vehicles both clean the same street, the length is counted only once toward your score — but both vehicles will have spent water on it, meaning you may incur waste twice. Avoid redundant cleaning.

## Rules Summary

- Every vehicle must start at the depot and return to the depot within time **T**.
- Vehicles may only move along streets that exist in the graph, respecting one-way directions.
- All mandatory streets must be cleaned. A solution is invalid otherwise.
- A vehicle can only clean a street if its capacity meets or exceeds the street's cleaning requirement.
- Any vehicle may traverse any street without cleaning it, at no water cost.
- Each street needs to be cleaned at most once.
- A vehicle's route is a sequence of junctions connected by valid streets, starting and ending at the depot.
- All vehicles travel at the same speed; traversal times are properties of streets, not vehicles.
- Vehicles have unlimited water supply; water waste is penalized in the score, not enforced as a hard constraint.

## Input Data Set

### File Format

Each input data set is provided in a plain text file containing only ASCII characters with lines ending with a single `\n` character (UNIX-style line endings). When multiple values are given on one line, they are separated by a single space.

The first line of the data set contains:

- **N** (`1 ≤ N ≤ 10⁴`) — the number of junctions
- **M** (`1 ≤ M ≤ 10⁵`) — the number of streets
- **T** (`1 ≤ T ≤ 10⁶`) — the time limit in seconds
- **C** (`1 ≤ C ≤ 10²`) — the number of vehicles in the fleet
- **S** (`0 ≤ S < N`) — the index of the depot junction
- **α** (`0 ≤ α ≤ 1`) — the weight balancing coverage vs. water efficiency in the scoring formula

This is followed by **N** lines describing individual junctions. The i-th such line contains two decimal numbers representing the geographic coordinates of the junction.

This is followed by **M** lines describing individual streets. The j-th such line contains the following values separated by single spaces:

- **Aⱼ** and **Bⱼ** (`0 ≤ Aⱼ, Bⱼ < N, Aⱼ ≠ Bⱼ`) — the two junctions connected by the street.
- **Dⱼ** — either `1` or `2`. If `Dⱼ = 1`, the street is one-way (Aⱼ → Bⱼ only). If `Dⱼ = 2`, it is two-way.
- **Cⱼ** (`1 ≤ Cⱼ ≤ 10⁴`) — the traversal time in seconds.
- **Lⱼ** (`0 ≤ Lⱼ ≤ 10⁴`) — the length in meters. Connector streets have length 0.
- **Catⱼ** — the category: `M` (mandatory), `O` (optional), or `C` (connector).
- **Rⱼ** — the cleaning requirement: `10`, `20`, or `30` (liters/km). For connector streets, this value is `0` and should be ignored.

The last line of the input contains **C** characters separated by spaces, each being `S`, `M`, or `L`, describing the type of each vehicle in the fleet.

### Example Input

```
6 10 300 3 0 0.5
0 1 2 30 200 M 10
1 3 2 25 150 O 10
1 2 2 35 300 M 20
0 3 1 20 0 C 0
3 5 2 15 100 O 10
2 4 2 30 250 M 30
3 4 2 40 350 O 20
4 5 2 20 0 C 0
5 2 2 45 400 O 30
5 0 2 25 0 C 0
S M L
```

| Street | Description |
|---|---|
| Street 0 | Junctions 0–1, two-way, 30 s, 200 m, Mandatory, req. 10 |
| Street 1 | Junctions 1–3, two-way, 25 s, 150 m, Optional, req. 10 |
| Street 2 | Junctions 1–2, two-way, 35 s, 300 m, Mandatory, req. 20 |
| Street 3 | Junctions 0→3, one-way, 20 s, Connector |
| Street 4 | Junctions 3–5, two-way, 15 s, 100 m, Optional, req. 10 |
| Street 5 | Junctions 2–4, two-way, 30 s, 250 m, Mandatory, req. 30 |
| Street 6 | Junctions 3–4, two-way, 40 s, 350 m, Optional, req. 20 |
| Street 7 | Junctions 4–5, two-way, 20 s, Connector |
| Street 8 | Junctions 5–2, two-way, 45 s, 400 m, Optional, req. 30 |
| Street 9 | Junctions 5–0, two-way, 25 s, Connector |

> This example corresponds to a small section of the city of Podujeva. It contains 3 mandatory streets, 4 optional streets, and 3 connector streets.

## Submissions

### File Format

Your submission describes the route taken by each vehicle and which streets it cleans along the way.

The submission file must start with a line containing the integer **C** — the number of vehicles in the fleet (must match the input).

Then, for each vehicle (in order from vehicle 1 to vehicle C), the file must contain three lines:

1. **n** (`1 ≤ n ≤ 10⁶`) — the number of junctions in the vehicle's route (including the depot at start and end).
2. **n junction indices** in order, starting and ending with **S**. Each consecutive pair of junctions must be connected by a valid street.
3. The **indices of the streets** that this vehicle cleans along its route (a subset of the streets it traverses). If the vehicle cleans no streets, this line is left empty.

> You don't need every vehicle to clean streets — some vehicles may just traverse the network. If a street is cleaned by more than one vehicle, the solution is still accepted but the score for that street is counted only once. Streets cleaned after the time limit or by vehicles that do not return to the depot are ignored.

### Example Submission

```
3
4
0 1 3 5 0
0 1 4
5
0 1 2 4 5 0
2
8
0 1 2 4 5 2 4 5 0
5 8
```

| Vehicle | Route | Cleans |
|---|---|---|
| Vehicle 1 | depot → 1 → 3 → 5 → depot | Streets 0, 1, 4 |
| Vehicle 2 | depot → 1 → 2 → 4 → 5 → depot | Street 2 |
| Vehicle 3 | depot → 1 → 2 → 4 → 5 → 2 → 4 → 5 → depot | Streets 5, 8 |

## Scoring

Your score is computed as a weighted sum of two normalized objectives, both to be **maximized**:

```
Score = α × Coverage + (1 − α) × Efficiency
```

Where:

- **Coverage** measures how much of the cleanable street network you cleaned, normalized to [0, 1]:

  ```
  Coverage = (total length of cleaned streets) / L_max
  ```

  **L_max** = the sum of lengths of all mandatory and optional streets in the instance. This is the theoretical maximum length you could clean.

- **Efficiency** measures how little water you wasted, normalized to [0, 1]:

  ```
  Efficiency = 1 − (total water wasted) / W_max
  ```

  **Total water wasted** = the sum, over all cleaned streets, of `(vehicle capacity − street requirement) × street length in km`.

  **W_max** = the total water that would be wasted if every mandatory and optional street were cleaned by a Large vehicle (30 L/km). This is the worst-case waste and serves as the normalization upper bound:

  ```
  W_max = Σ (30 − Rⱼ) × Lⱼ / 1000    for all mandatory and optional streets j
  ```

  An efficiency of 1 means zero waste (every street cleaned by the smallest sufficient vehicle). An efficiency of 0 means maximum possible waste.

- **α** (`0 ≤ α ≤ 1`) = a weighting factor that controls the trade-off between coverage and efficiency. Its value is defined per problem instance and is given in the input file. When α = 1, only coverage matters. When α = 0, only efficiency matters.

A higher score is always better. The optimal strategy cleans all mandatory streets, cleans as many optional streets as possible, and assigns the smallest sufficient vehicle to each street.

**Validity:** A submission is invalid (and scores zero) if any mandatory street is left uncleaned, if any vehicle does not start and end at the depot, if any vehicle exceeds the time limit, or if any vehicle cleans a street whose requirement exceeds its capacity.

### Example Scoring

Based on the example input and submission above:

| Street | Category | Length | Cleaned By | Requirement | Vehicle Capacity | Waste |
|---|---|---|---|---|---|---|
| S0 (0–1) | Mandatory | 200 m | Vehicle 1 (S) | 10 L/km | 10 L/km | 0 L |
| S1 (1–3) | Optional | 150 m | Vehicle 1 (S) | 10 L/km | 10 L/km | 0 L |
| S2 (1–2) | Mandatory | 300 m | Vehicle 2 (M) | 20 L/km | 20 L/km | 0 L |
| S4 (3–5) | Optional | 100 m | Vehicle 1 (S) | 10 L/km | 10 L/km | 0 L |
| S5 (2–4) | Mandatory | 250 m | Vehicle 3 (L) | 30 L/km | 30 L/km | 0 L |
| S8 (5–2) | Optional | 400 m | Vehicle 3 (L) | 30 L/km | 30 L/km | 0 L |

All 3 mandatory streets are cleaned. ✔  
All vehicles return to the depot within 300 seconds. ✔

**Normalization bounds:**

```
L_max = 200 + 150 + 300 + 100 + 250 + 350 + 400 = 1,750 meters

W_max = (30−10)×0.200 + (30−10)×0.150 + (30−20)×0.300 + (30−10)×0.100
      + (30−30)×0.250 + (30−20)×0.350 + (30−30)×0.400
      = 4.0 + 3.0 + 3.0 + 2.0 + 0 + 3.5 + 0
      = 15.5 liters
```

**Score calculation:**

```
Total length cleaned = 200 + 150 + 300 + 100 + 250 + 400 = 1,400 meters
Total water wasted = 0 liters

Coverage  = 1,400 / 1,750 = 0.800
Efficiency = 1 − 0 / 15.5 = 1.000

With α = 0.5:
Score = 0.5 × 0.800 + 0.5 × 1.000 = 0.900
```

This solution achieves perfect efficiency (zero waste) because every street is cleaned by the smallest vehicle capable of handling it. Coverage is 0.8 because Street S6 (optional, 350 m) was left uncleaned due to time constraints. A perfect score of 1.0 would require cleaning all streets with zero waste.

### Example Timeline

- **Vehicle 1 (Small):** depot → 1 → 3 → 5 → depot. Cleans streets S0, S1, S4. Total time: 30 + 25 + 15 + 25 = **95 seconds**.
- **Vehicle 2 (Medium):** depot → 1 → 2 → 4 → 5 → depot. Cleans street S2 (traverses S0, S5, S7, S9 without cleaning). Total time: 30 + 35 + 30 + 20 + 25 = **140 seconds**.
- **Vehicle 3 (Large):** depot → 1 → 2 → 4 → 5 → 2 → 4 → 5 → depot. Cleans streets S5 and S8. Total time: 30 + 35 + 30 + 20 + 45 + 30 + 20 + 25 = **235 seconds**.

---

> **Note:** There are multiple data sets representing separate instances of the problem. The final score for your team will be the sum of your best scores for the individual data sets.