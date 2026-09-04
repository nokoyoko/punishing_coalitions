# Validation

The no-punishment check uses the Eyal--Sirer apparent-hashrate expression

`[a(1-a)^2(4a + gamma(1-2a)) - a^3] / [1 - a(1 + (2-a)a)]`

for `a < 1/2`, fixed hash power, instantaneous publication, zero natural-fork
rate, and the standard
state machine. `punishment_sim.theory.selfish_revenue` is the single executable
definition. The validation command tests alpha 0.15, 0.25, 0.35 crossed with
gamma 0, 0.5, 1.0, using independent repetitions. It writes the analytic value,
sample mean, standard error, and Student-t 95% interval. Sampling intervals are estimates,
not proofs; increase accepted blocks and repetitions for publication results.

Short development checks at 10,000 accepted blocks included:

| alpha | gamma | simulated | analytic |
|---:|---:|---:|---:|
| 0.15 | 0.0 | 0.0743 | 0.0763 |
| 0.25 | 0.5 | 0.2506 | 0.2500 |
| 0.35 | 1.0 | 0.4643 | 0.4656 |

The ordinary suite separately checks accounting/ancestry invariants, seeded
reproducibility, detector extremes, deterministic lead/race transitions,
punishment activation, persistent miner-level labels, natural-fork punishment
opportunities, pure-type separation, event accounting, race-origin counts,
algebraic TPR/FPR mixing, reuse of four conditional mining runs across detector
grids, and honest-mining convergence. The formula validates the
unpunished strategy and tie semantics only. No external analytic result yet
validates the noisy miner classifier or petty-punishment equilibrium; those are tested
by deterministic branch choices and probability-direction diagnostics. The
miner-type ground-truth rule and reduced-form propagation rate remain documented
modeling assumptions.
