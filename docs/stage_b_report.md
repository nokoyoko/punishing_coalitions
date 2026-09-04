# Stage B petty tie-breaking sweep

Stage B executed the complete configured aggregate and coalition-composition
grids with 30 independent repetitions and 30,000 accepted blocks per
conditional simulation. Petty tie-breaking was the only punishment rule.

The dry run requested 2,142 population configurations, which deduplicated to
1,980 behaviorally unique populations and 5,544 nonempty coalition conditions.
There were 700,380 conditional-environment requests, 451,440 unique mining
simulations, 248,940 cache hits, 110,880 algebraic detector evaluations, and
13,543,200,000 accepted-block work units. Actual cache counts matched exactly.

Eight local worker processes wrote resumable per-population checkpoints. The
mining and initial assembly run took 8,532.58 seconds. Final outputs occupy
approximately 2.4 GiB, including checkpoints and structured JSON.

All twelve output-completeness questions are directly answerable from emitted
tables and repetition metrics. The Stage C candidate table is capped at 250
ranked, unresolved cases; Stage C was not launched.

Credibility uses the validated comparison `U_j^{S,C} - U_j^{S,empty}` for the
baseline margin and `U_j^{S,C} - U_j^{S,C-minus-j}` for deviation-proof
credibility, calculated within matched repetitions. The leave-one-out miner
remains an explicit independent candidate but ceases punishment. The validated
status convention regards an exact-zero confidence-interval lower bound as
supported and point credibility uses a nonnegative margin. Consequently,
zero-slack credible rows are not evidence of strictly profitable participation.

Protocol-payoff tolerance is a modeled block-reward margin only. It excludes
communication, coordination, monitoring, implementation, and enforcement costs
and is not a real-world cost estimate.
