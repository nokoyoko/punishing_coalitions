# Winning-coalition definition audit

The corrected simulator computes paired 95% Student-t intervals over independent
repetitions. The historical stored fields mean:

- `effectiveness_status == SUPPORTED`: the target deterrence interval
  `U_H - U_SC` has a strictly positive lower endpoint.
- `baseline_credible`: every active member's baseline margin `U_SC - U_S0` is
  historically `SUPPORTED` (nonnegative CI rule in `status`).
- `deviation_proof`: every active member's deviation margin
  `U_SC - U_leave-one-out` is historically `SUPPORTED`.
- historical `winning`: the coalition is nonempty, effectiveness is strictly
  supported, and historical `deviation_proof` holds. It does **not** require
  `baseline_credible`.
- historical `minimal_winning_coalition`: a historical winning coalition with
  no proper-subset historical winning coalition in the same configured
  population. This is set minimality, not merely minimum total hash.

No historical field was modified. The core analysis adds derived terminology:

- `EFFECTIVE`: corrected `effectiveness_status == SUPPORTED`.
- `BASELINE_CREDIBLE`: all active members meet the refined weak baseline rule
  (`baseline CI low >= -1e-12`).
- `DEVIATION_PROOF` and new-analysis `WINNING`: all active members weakly prefer
  remaining, using the refined weak deviation rule (`CI low >= -1e-12`).
- `STRICTLY_DEVIATION_PROOF`: every member's deviation CI lower endpoint is
  greater than `1e-12`.
- `JOINTLY_FEASIBLE`: `EFFECTIVE AND BASELINE_CREDIBLE AND DEVIATION_PROOF`.
- `STRICTLY_JOINTLY_FEASIBLE`: `EFFECTIVE`, refined strict baseline credibility,
  and `STRICTLY_DEVIATION_PROOF` all hold.

Active coalition power is always the sum of active members. Candidate-population
power is retained separately and is never substituted for it.
