# Malisheva image-derived instance

`data/input/malisheva.txt` is a hand-digitized, map-faithful benchmark derived
from the supplied Malisheva map image. It is not claimed to be survey-grade GIS or
OpenStreetMap data.

## Modeling choices

- Junction `0` is the central depot at the map pin.
- The accepted dataset schema omits coordinates. Image-plane coordinates were used
  during digitization but are not serialized into the final instance.
- The west-east and north-south yellow arterial corridors are Heavy mandatory
  streets.
- Visible urban collectors connecting neighborhoods are primarily Medium mandatory
  streets.
- Residential branches and outer/rural roads are Optional Light or Medium streets.
- Four short river/central crossings are movement-only connectors.
- Several central/eastern streets are one-way to exercise directed routing.
- Direction encoding matches the accepted training files: `1` is one-way and `2`
  is two-way.
- Travel times use faster arterial and slower residential assumptions rather than
  deriving speed from image pixels alone.

## Instance summary

```text
Junctions: 36
Streets:   73
Vehicles:  5 (S, M, M, L, L)
Time:      400 seconds per vehicle
Alpha:     0.7
Depot:     0
```

The instance intentionally contains enough mandatory arterial/collector work to
require multiple vehicles while leaving competition for optional neighborhood
coverage. Total cleanable service time is 2,167 seconds, exceeding the aggregate
2,000-second fleet budget even before connector and depot-return travel, so a
perfect-coverage solution is impossible by construction.
