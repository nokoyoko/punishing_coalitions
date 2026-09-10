# Petty-punishment research sweep

`research-sweep` is a staged, conditional-payoff workflow. Mining is run only
for behaviorally distinct configurations; TPR, FPR, and optional prior values
are algebraic evaluations over the cached four conditional payoff vectors.
Cache keys include target/candidate powers, gamma, natural-fork rate, block
target, repetition seed, strategy, persistent label, and active coalition. They
exclude detector-quality parameters.

The development configuration uses 10 repetitions and 10,000 accepted blocks.
The supplied research configuration uses 30 repetitions and 50,000 blocks, and
the production template is intentionally not executed automatically. Dry-run
estimates report requested populations, valid and unique populations, conditional
environment requests, unique mining simulations, cache hits, detector
evaluations, and accepted-block work units.

The separate [refined v4 1%-resolution configuration](oceanic_v4_1pct_design.md)
uses exactly **20 repetitions for every top-level configuration** and 30,000
accepted blocks per simulation, with no staged follow-up. Its combinatorial
scope planner reports 250,170 configurations, 39,934,200 mining simulations and
1,198,026,000,000 accepted-block work units. It preserves paired uncertainty
outputs, using the df=19 Student-t interval for 20 repetitions. The historical
30-repetition checkpoint importer does not support first-20 prefix reuse.

`continuous_tpr_thresholds.csv` uses the conditional tuple-level formula and a
reproducible bootstrap over repetitions. `false_positive_vectors.csv` keeps
conditional actor losses separate from FPR-weighted expected costs. Composition
comparisons use matched active hash power and paired repetition differences.
Exact zero or sign-ambiguous composition differences are INCONCLUSIVE; the
generic credibility status remains separate from that hypothesis test.

Positive deviation-proof margins and the reported `protocol_payoff_tolerance`
are properties of the modeled block-reward game only. Communication,
coordination, monitoring, implementation, and enforcement costs are not
modeled, so qualitative robustness bins do not imply real-world significance.
