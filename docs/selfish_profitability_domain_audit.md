# Selfish-profitability domain audit

Profitability is computed from paired repetition differences:

`U_S0 - U_H = punishment_reduction - deterrence`.

This cancels the punished payoff algebraically and uses no punishment outcome
to classify the unpunished baseline. A paired Student-t 95% interval is formed
for each corrected aggregate population configuration.

The simulator does not provide one unique baseline at fixed `(alpha, gamma,
lambda)`: changing aggregate candidate power changes the explicit actor
partition and therefore which natural forks can occur. Of 90 desired
environments, 78 have unanimous representation-level classifications and 12
change classification across the 13 aggregate candidate-power representations.
Selecting one representation would be arbitrary.

The primary domain rule is consequently conservative and explicit:

- `SELFISH_PROFITABLE`: every corrected aggregate representation has paired CI
  strictly above zero;
- `SELFISH_NOT_PROFITABLE`: every representation has paired CI strictly below
  zero;
- `SELFISH_PROFITABILITY_INCONCLUSIVE`: any mixed or individually inconclusive
  representation set.

This yields 15 profitable, 63 not profitable, and 12 inconclusive environments.
All 15 unanimously profitable cells have alpha 0.35; every gamma and lambda is
represented. Lambda does not change the unanimous domain classification, but
it changes representation-level estimates and is retained independently.

The ambiguity is a model limitation, not Monte Carlo bookkeeping. Headline
claims should either use this conservative rule or first define a canonical
honest-population partition. The supplement uses only the 15 unanimous
profitable environments.
