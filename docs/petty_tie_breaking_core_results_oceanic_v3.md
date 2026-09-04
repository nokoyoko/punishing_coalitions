# Petty tie-breaking core results under oceanic residual v3

The v3 aggregate grid classifies 33 of 90 environments as statistically
profitable for unpunished selfish mining, 42 as not profitable, and 15 as
inconclusive. The composition grid was simulated for exactly the 33 profitable
triplets.

One profitable environment has a weakly jointly feasible coalition: alpha
0.20, gamma 1, lambda 0. Its minimum active hash is 0.30. All six structures
tie: `[0.30]`, `[0.15,0.15]`, `[0.075,0.225]`, `[0.10,0.10,0.10]`,
`[0.06,0.09,0.15]`, and `[0.03,0.06,0.21]`. Every tied coalition has zero
credibility slack, so none is strict. No strictly jointly feasible environment
was found.

The other 32 profitable environments have no jointly feasible coalition within
the tested grid. This is grid-bounded evidence, not a universal impossibility
result. For the six tied minima, continuous TPR ranges from 0.8287 to 0.8771.
At lambda 0.005 and 0.02 the sole feasible alpha/gamma pair loses feasibility.
No profitable-domain equal-active-hash pair flips joint or strict feasibility.

The aggregate sweep used 4.212 billion block work units and 1,942.6 seconds.
The composition sweep used 12.1176 billion gross units, reused 198 v3
checkpoints, created 990 new checkpoints, and ran for 7,417.5 seconds. Output
sizes are about 424 MiB and 2.8 GiB. No pre-v3 checkpoint or Stage C execution
was used.

The focused Stage C mapping has 38 rows: 32 environment nonexistence results
and six tied weak minima. Stage C was not launched.

Limitations include the finite 0.30 candidate-power ceiling, break-even weak
credibility, aggregate-representation effects under natural forks, no
residual-residual internal forks, simplified propagation, and no explicit
residual pool distribution.
