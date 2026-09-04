# Threshold interpretation

`threshold_audit.csv` rechecks all minimizers, active member-vector sums, ties,
and point/supported distinctions. It adds weak and strict baseline/deviation
credibility thresholds without interpolation.

Labels mean:

* `OBSERVED_INTERIOR`: the first qualifying observed active power is strictly
  inside the evaluated active-power support;
* `AT_LOWER_GRID_EDGE`: left-censored; the true threshold may be lower;
* `AT_UPPER_GRID_EDGE`: a boundary observation, not evidence that this grid
  point is the population minimum;
* `NOT_FOUND_WITHIN_GRID`: no observed coalition qualified; it is not a numeric
  threshold and does not prove one exists above the grid;
* `SELFISH_ALREADY_UNPROFITABLE`: the environment needs no punishment for the
  modeled target comparison;
* `NO_ELIGIBLE_COALITION`: no active coalition was available for the requested
  metric.

Candidate-population power is never substituted for active coalition power.
Minimizers retain configuration, coalition, member vector, cardinality, and
structure; ties are preserved. Censored and no-result surfaces should use
symbols rather than connected numeric interpolation in figures.
