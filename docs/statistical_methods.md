# Statistical methods

One simulation repetition—not an individual block—is the unit of analysis.
Block outcomes within a run are dependent through private lead, races, pending
propagation, and stopping. Thirty repetitions use distinct seeds and are
treated as approximately independent. Conditional environments at a common
repetition use deterministic common random numbers, inducing useful pairing;
state-dependent stream consumption means pairing is not literal event-by-event
identity after paths diverge.

In model version `race-owner-oceanic-residual-v3`, explicit ownership and deterministic petty
decisions do not consume tie-choice randomness. Neutral explicit and oceanic-residual gamma or benign
50/50 decisions consume that stream. This corrects prior unnecessary owner
draws consume it; the residual aggregate never gains ownership. Paired environments remain meaningfully seeded but may realign or
diverge state-dependently after different race decisions.

Deterrence, punishment reduction, both member credibility margins,
false-positive loss, and equal-active-hash payoff comparisons first construct
one matched difference per repetition. The reported mean, standard error, and
two-sided 95% interval are then calculated across those 30 differences using
the hard-coded df=29 Student-t critical value 2.045. No endpoints from separate
payoff intervals are subtracted. No within-run blocks are treated as iid.

Continuous TPR uncertainty jointly resamples complete `(H,S0,SC)` repetition
tuples. Stage B uses 2,000 deterministic bootstrap draws, recomputes the ratio
from resampled tuple means, excludes draws that do not satisfy the deterrable
ratio regime, counts valid/invalid draws, and reports 2.5/97.5 percentiles.

For the exploratory composition audit, two-sided p-values are derived from the
paired Student-t statistic and df=29. Benjamini–Hochberg FDR adjustment at 0.05
is performed separately within five prespecified metric families, each with
4,050 tests. Original differences, intervals, p-values, and unadjusted statuses
remain in `equal_hash_comparisons_adjusted.csv`.

Simulation estimates remain random because finite discovery, natural-fork, and
tie streams are sampled. Student-t coverage and bootstrap percentile coverage
are approximate at 30 repetitions. Selection, threshold minimization, and the
minimum-member operation add post-selection uncertainty not captured by a
single member interval.
