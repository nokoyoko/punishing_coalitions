# Explicit coalition study

The explicit engine represents target, each candidate `c_j`, and one
`honest_residual` actor separately. Candidates never pool hash power or rewards.
Membership in active C changes only that miner's target-involved tie choice.
Blocks and rewards retain exact owner IDs. Natural forks occur between any
distinct honest-publishing represented actors; a selfish target is excluded,
while candidates may fork with each other and the residual actor.

For each repetition the study caches conditional environments by target
strategy, forced label, active subset, and complete population/network key. It
reuses U^H and U^(S,empty), all coalition runs, and leave-one-out runs. A shared
repetition seed drives identically derived discovery uniforms in every
counterfactual. Event paths can consume those aligned uniforms differently once
strategies change, so this is common-stream coupling rather than guaranteed
block-for-block synchronization.

For every C it estimates paired repetition differences: deterrence
`U_target^H-U_target^(S,C)`, punishment reduction
`U_target^(S,empty)-U_target^(S,C)`, member baseline credibility
`U_j^(S,C)-U_j^(S,empty)`, and deviation credibility
`U_j^(S,C)-U_j^(S,C-minus-j)`. Student-t intervals produce SUPPORTED,
INCONCLUSIVE, or REFUTED statuses. Winning requires statistically supported
strict effectiveness and supported deviation credibility for every member.
Empty-coalition credibility is vacuous; singleton baseline and deviation
comparisons coincide.

TPR and FPR are algebraic outer parameters. TPR mixes selfish empty/punished
payoffs; FPR mixes honest benchmark/false-positive enforcement payoffs. No
unconditional honest/selfish mixture is emitted without `selfish_prior`.
Outputs preserve conditional, detector-quality, member, and repetition rows.
False-positive output distinguishes the conditional cost vector
`U(H,unflagged)-U(H,flagged,C)` from its FPR-weighted expected cost vector;
the latter is exactly FPR times the former for target, every candidate, and the
residual honest actor.

Paired statistics also report the paired-difference variance, the independent
variance estimate `Var(X)+Var(Y)`, proportional variance reduction from common
streams, and a flag when coupling increases variance. Transition reports retain
the weakest member and minimum deviation margin and select production follow-up
only for confidence intervals that still cross zero.

Small populations enumerate every subset canonically. Larger exact enumeration
is capped; users should supply screened subsets in a later extension. Sweep
configuration accepts explicit shares or equal, moderately unequal, and
one-large-many-small distributions. Dry-run reports simulation and algebraic
evaluation counts. Configuration hashes provide deterministic IDs; output files
are configuration-level checkpoints that can be retained when restarting.

Threshold metadata retains coalition composition for minimum point-estimate and
statistically supported effective, baseline-credible, deviation-proof, and
TPR-expected-effective coalitions. Minimal winning coalitions exclude the empty
coalition.

Current limitations include aggregate residual-honest behavior, no within-actor
natural forks, no side payments or reward transfers, no pooled mining, and the
provisional convention that a selfish target resolves a target-free natural tie
normally before resuming selfish mining. Transferable utility, Shapley/Banzhaf
indices, core analysis, retaliation, multiple attackers, and endogenous
coalition formation remain out of scope.

Positive deviation-proof payoff differences establish credibility only within
the modeled block-reward game. The simulator does not include communication,
coordination, monitoring, implementation, or enforcement costs. A coalition
with a very small positive deviation margin may therefore cease to be credible
after external costs are introduced.

Sweep reports call the minimum member deviation margin a protocol-payoff
tolerance. It is the maximum per-block-revenue participation cost supported by
the modeled payoff inequality, not an estimate of communication, coordination,
monitoring, implementation, enforcement, or other real-world costs. Descriptive
robustness bins preserve the exact margin and do not assert economic significance.
