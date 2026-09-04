# Oceanic-residual selfish-mining validation

Model `race-owner-oceanic-residual-v3` was tested at lambda zero against the
Eyal–Sirer threshold `(1-gamma)/(3-2 gamma)`. Fifteen targeted points used 40
paired repetitions and 100,000 accepted blocks per honest/selfish simulation.
All 15 matched the expected side of the theoretical boundary; points exactly
on the boundary at `(alpha,gamma)=(0.30,0.25)` and `(0.25,0.5)` were correctly
inconclusive.

The critical `(alpha,gamma)=(0.30,0.5)` point is profitable: simulated honest
payoff 0.3001795, unpunished selfish payoff 0.3268185, difference 0.0266390,
95% paired CI `[0.0262574, 0.0270207]`.

The complete results are in
`results/residual_oceanic_validation/eyal_sirer_threshold_validation.csv`.
The benchmark uses one negligible explicit honest actor (hash 0.001) plus the
oceanic residual. At lambda zero that partition cannot generate natural-fork
differences. No residual-residual internal fork mechanism was introduced.
