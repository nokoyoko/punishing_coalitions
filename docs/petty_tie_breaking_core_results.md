# Petty tie-breaking: core coalition-formation results

This report uses only corrected `race-owner-precedence-v2` outputs. The unit of
the central conclusion is an `(alpha, gamma, lambda)` mining environment, not
an individual simulation condition.

## 1. When is selfish mining profitable without punishment?

The aggregate corrected surface remains the appropriate answer to this first
question. Within the 90 aggregate environments, 63 are classified as already
unprofitable. This does not establish coalition feasibility, which additionally
requires explicitly modeled members and their participation evidence.

## 2. When can petty tie-breaking deter it?

Every one of the 27 environments actually covered by the composition sweep has
at least one statistically supported effective coalition. These environments
cover alpha 0.20, 0.25, and 0.30; gamma 0, 0.5, and 1; and all three lambda
values. Results outside that composition grid are marked `OUTSIDE_COMPOSITION_GRID`.

## 3. When does a willing, nondeviating coalition exist?

`JOINTLY_FEASIBLE` requires supported deterrence, refined weak baseline
credibility for every member, and refined weak deviation-proof status for every
member. Such a coalition exists in 23 of the 27 covered environments. Two
environments have effective coalitions but no baseline-credible coalition; two
reach baseline credibility but not deviation-proof participation.

A `STRICTLY_JOINTLY_FEASIBLE` coalition exists in 17 of 27 environments. Six
additional environments are feasible only under weak/break-even participation.
This distinction is central: weak feasibility does not imply a positive
participation-cost tolerance.

## 4. What are the minimum coalitions?

The minimum table retains every tied composition at the lowest **active** hash,
not candidate-population hash. Across covered environments the observed weak
minimum ranges from 0.005 to approximately 0.0667. For example, at alpha 0.25,
gamma 0.5, lambda 0, the first weak and strict jointly feasible coalition has
active hash 0.02. At the same alpha and gamma with lambda 0.02, the minimum is
0.05. Exact member identities, inactive candidates, member margins, slack,
TPR, false-positive loss, and boundary flags are in
`minimum_feasible_coalitions.csv` and `feasible_coalition_compositions.csv`.

There are 203 matched-active-hash pairs where composition changes joint
feasibility. Thus composition can matter to coalition formation in specific
conditions, without implying universal composition dependence.

## 5. Robustness

Lambda changes feasibility existence or the observed minimum in all nine
covered alpha/gamma pairs, recorded as 27 lambda-specific rows. Lambda is
therefore shown as a robustness panel rather than pooled into the main result.
Continuous and configured detector requirements are computed algebraically from
existing detector outputs; no mining was rerun. Already-unprofitable cases stay
categorical, and failure at TPR 1 cannot count as detector-adjusted feasible.

Coverage is the primary unresolved issue. Only 27 of the desired 90 central
cells have composition enumeration. The 63 missing cells comprise alpha 0.10,
0.15, and 0.35 at every gamma, plus gamma 0.25 and 0.75 for alpha 0.20--0.30.
A planning-only supplemental config and conservative dry-run estimate were
created. They request 2,268 population configurations, estimate 1,890 new
populations, 491,400 mining simulations, 14.742 billion accepted-block work
units, roughly 7,827 seconds, and 2.94 GiB. These are planning estimates—not an
executed experiment—and should be confirmed by the repository dry-run engine
before any launch.

The old 5,388-case candidate inventory remains available but is not the default
plan. The central-question list contains eight cases, each tied directly to a
minimum, existence, weak/strict, TPR, grid, or terminal-sensitive headline.

## Recommended core outputs

1. `joint_feasibility_map`
2. `strict_joint_feasibility_map`
3. `weak_vs_strict_joint_feasibility`
4. `minimum_joint_feasible_power_vs_attacker`
5. `joint_feasible_tpr_requirements`
6. `feasible_coalition_compositions.csv` as the identity table

The earlier 27 figure families remain exploratory/supporting outputs.

Limitations include incomplete composition coverage, finite-grid censoring,
weak criteria that permit break-even margins, simplified propagation, no
residual-honest internal forks, and no implementation-cost model.
