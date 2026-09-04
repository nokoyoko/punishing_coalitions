# Equal-active-hash composition effects

The corrected `race-owner-precedence-v2` audit analyzes 4,050 directly paired comparisons per payoff family, holding
target power, gamma, lambda, candidate-population power, active power,
accepted-block target, repetitions, and behavioral settings fixed.

Corrected deterrence median absolute difference is `1.25e-5`, 95th percentile
`3.61e-4`, and maximum `0.003998`; 217 positive and 140 negative comparisons
survive within-family BH. Corrected punishment reduction median absolute effect
is `9.67e-5`, 95th percentile `0.00351`, maximum `0.01315`, with 1,047 positive
and 1,023 negative BH-supported comparisons. Aggregate active power remains
important, but the corrected data do not support a broad composition-invariance
claim.

Corrected baseline-margin BH counts are 897 positive and 975 negative;
deviation/slack counts are 236 positive and 286 negative. Corresponding 95th
percentile absolute effects are `0.00129` and `0.000220`. Signs remain mixed, so
no structure is declared generally superior.

`composition_effect_summary.csv` provides overall and structure-pair, target,
gamma, lambda, and active-power facets with effect distributions. Neighboring
directional consistency should be treated as exploratory because comparisons
overlap and share configurations. Statistical significance is not economic
importance; payoff-share effects should be shown on an explicit scale.
