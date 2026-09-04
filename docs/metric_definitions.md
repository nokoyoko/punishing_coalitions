# Metric definitions and credibility refinement

The machine-readable audit is `results/research_sweep_stage_b/metric_definition_audit.csv`.
Every payoff is an accepted-block revenue share computed within one repetition.
The current behavioral model is `race-owner-oceanic-residual-v3`. Archived v2
outputs retain their original label and are not inputs to v3 conclusions.

* Deterrence is `D_i^P(C)=U_i^H-U_i^{S,C}`.
* Punishment reduction is `R_i^P(C)=U_i^{S,empty}-U_i^{S,C}`.
* The stored “baseline credibility” margin is
  `B_j^P(C)=U_j^{S,C}-U_j^{S,empty}`. In the first environment the target is
  selfish, persistently flagged, and all members of C punish. In the second the
  target is selfish and unflagged and **no coalition member punishes**. Thus
  other members do not remain active in the baseline. Both environments retain
  every candidate identity, target strategy, gamma, lambda, and repetition seed.
  “Coalition participation gain relative to the unpunished selfish baseline” is
  a more precise interpretive name; stored values were not renamed.
* Deviation credibility is
  `Q_j^P(C)=U_j^{S,C}-U_j^{S,C\{j}}`. Miner j retains identity, hash, honest
  mining, and individual rewards, but stops overriding gamma; other active
  members continue punishment.
* Slack is `kappa^P(C)=min_j mean(Q_j^P(C))`. Member intervals remain the
  inferential basis; the minimum of means is a descriptive coalition summary.
* False-positive loss is `L_FP,a=U_a^H-U_a^{H,F,C}` for every represented actor.
* Continuous TPR is the conditional-payoff ratio, with documented edge cases.

Paired differences are formed within repetition before Student-t aggregation.
The refined tables use epsilon `1e-12` and distinguish:

* `STRICTLY_SUPPORTED`: CI lower bound `> epsilon`;
* `WEAK_BREAK_EVEN`: point and both endpoints within epsilon of zero;
* `WEAKLY_NONNEGATIVE`: lower bound at least `-epsilon`, but neither of the above;
* `INCONCLUSIVE`: interval includes a materially negative value and a
  nonnegative value;
* `REFUTED`: upper bound `< -epsilon`.

Separate point-nonnegative, CI-nonnegative, CI-strictly-positive, weak, and
strict booleans are retained. A coalition is weakly deviation-proof only if all
members are weakly supported, and strictly deviation-proof only if all are
strictly supported. A zero-slack coalition has zero refined protocol-payoff
cost tolerance and must not be described as profitable or robust.

The prior `baseline_status` and `deviation_status` fields are retained for
reproducibility. Use `member_credibility_refined.csv` and
`coalition_credibility_refined.csv` for interpretation.
