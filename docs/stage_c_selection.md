# Stage C selection audit

The original 250-row selector used three reasons: effectiveness CI crossing
zero, point-winning without supported credibility, and a continuous-TPR
interval crossing a reporting-grid TPR. It sorted by reason priority, target,
gamma, lambda, active power, configuration, and coalition, then took the first
250. It did not enforce representation or protect publication-critical cases.

For the corrected model, the uncapped audit expands reason codes to credibility, threshold-boundary,
TPR-width/transition, equal-hash multiplicity disagreement, near-zero slack,
and extreme false-positive exposure. It identifies 5,388 candidates. Direct
reason categories are publication-critical threshold confirmation, unresolved
credibility margin, detector-threshold transition, composition comparison, and
boundary/anomaly review. Optional ranking metadata protects all 429
publication-critical cases rather than deleting one solely because of a cap.
Stage C was not launched.

Optional tier definitions:

* Tier 1: effectiveness transition, threshold boundary, point-versus-supported
  publication disagreement, or TPR interval crossing a reporting value.
* Tier 2: unresolved structural/multiplicity comparisons, weak-versus-strict
  credibility disagreement, wide TPR, or near-zero slack.
* Tier 3: robustness and extreme false-positive exposure.

Conservative deduplicated production estimates at 50 repetitions and 100,000
accepted blocks are: Tier 1, 89,850 conditional simulations/8.985 billion work
units/~5,661 seconds/~1.66 GiB; Tier 2, 785,400/78.54 billion/~49,482 seconds/
~14.50 GiB; no candidates are assigned Tier 3 after higher-priority reason
coalescing. These extrapolate
Stage B throughput and storage and remain planning estimates.
