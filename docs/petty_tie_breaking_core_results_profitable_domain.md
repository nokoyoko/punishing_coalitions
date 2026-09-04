# Petty tie-breaking in the profitable-selfish-mining domain

## Where is unpunished selfish mining profitable?

Profitability is classified from paired repetition differences `U_S0-U_H`, not
from punishment outcomes. Because the aggregate actor partition changes with
candidate power, 12 of 90 environments have representation-dependent or
inconclusive classifications. The conservative primary rule requires every
corrected aggregate representation's paired CI to support the same conclusion.

The result is 15 statistically supported profitable environments, 63 not
profitable environments, and 12 inconclusive environments. The 15 profitable
environments all have alpha 0.35 and span every gamma and lambda value.

## Can petty tie-breaking deter profitable selfish mining?

The targeted supplement enumerated all six candidate totals, six structures,
and every nonempty coalition in all 15 profitable environments. Effective
coalitions exist, but effectiveness alone is not coalition formation.

## Can a credible, deviation-proof coalition form?

No. None of the 15 statistically profitable environments contains a coalition
that simultaneously has supported deterrence, refined weak baseline
credibility for every member, and refined weak deviation-proof participation
for every member. Therefore none is strictly jointly feasible either.

The central corrected conclusion is:

> For alpha 0.35 across gamma in {0, 0.25, 0.5, 0.75, 1} and lambda in
> {0, 0.005, 0.02}, unpunished selfish mining is statistically supported as
> profitable, but no jointly feasible petty tie-breaking coalition was found
> within the tested candidate and coalition grid.

This is `NO_FEASIBLE_COALITION_WITHIN_TESTED_GRID`, not proof that no possible
coalition exists outside the grid.

## Minimum coalition and composition

There is no minimum jointly feasible active hash or attaining composition in
the profitable domain because the qualifying set is empty. Accordingly,
already-unprofitable environments are not plotted as zero coalition power.
Equal-active-hash composition comparisons yield no cases where composition
flips weak or strict joint feasibility within the profitable domain: every
tested composition fails the conjunction. This does not imply payoff-level
composition invariance.

## Detector requirement

Continuous TPR for a minimum viable coalition is undefined because no viable
coalition exists. The profitable-domain TPR figure is intentionally empty and
annotated rather than substituting zero or including already-safe controls.

## Lambda robustness

Lambda is classified independently. It does not change the conservative
profitability-domain membership for alpha 0.35, and no jointly feasible
coalition appears at any tested lambda. Thus the no-feasible-coalition result is
qualitatively robust over the tested lambda values.

## Supplemental execution

The native dry run requested 540 populations and 183,600 unique simulations.
Ninety behaviorally identical corrected singleton checkpoints were reused; 450
new population checkpoints required 172,800 unique simulations and 5.184
billion accepted-block work units. Runtime was 3,753.5 seconds and the result
directory occupies approximately 1.3 GiB. This avoided about 64.8% of the
14.742-billion-block blind supplement estimate. No pre-fix checkpoint was
used, and Stage C was not executed.

The focused Stage C table contains 15 environment-level cases, each tied to the
headline conclusion that no feasible coalition was found. Confirmation could
tighten that conclusion but should not be conflated with extending the tested
coalition grid.

Remaining questions are the baseline actor-partition ambiguity, finite
candidate grid, weak credibility criterion, simplified propagation, and the
absence of residual-honest internal forks.
