# Target-race owner-precedence defect

This documents the historical v2 correction. Its treatment of the residual
aggregate as a persistent owner was superseded by oceanic-residual v3; see
`residual_oceanic_gamma_defect.md`.

## Pre-modification audit

Target-involving races were resolved in `ExplicitSimulation.step`. The old
ordering was: target finder chooses target; flagged active finder chooses the
other block; every remaining finder samples gamma. Ownership checks appeared
only in the subsequent benign-race branch. Consequently, an inactive candidate,
leave-one-out miner, or residual actor that owned the competing target-race
sibling could abandon its own block according to gamma. Explicit and residual
actors used this same branch.

Minimal prior trace: target owns sibling A, inactive `c1` owns sibling B, and
`c1` finds the resolving block. At gamma 1 the old target-race branch sampled
the tie stream and chose A, orphaning `c1`'s own B. The corrected decision is B
with reason `OWN_COMPETING_BRANCH`, at both gamma 0 and gamma 1, without a tie
random draw.

## Correction

`_choose_race_branch` now implements one testable precedence:

1. target owns/extends the target sibling (`OWN_TARGET_BRANCH`);
2. competing owner extends its sibling (`OWN_COMPETING_BRANCH`);
3. a neutral flagged active member punishes (`PETTY_PUNISH_TARGET`);
4. a neutral actor uses gamma (`NEUTRAL_GAMMA_TARGET|COMPETING`).

An active candidate owning the target sibling is unreachable: candidate IDs
cannot be `target`, and target blocks are owned only by that reserved identity.
Benign owner loyalty and neutral 50/50 behavior are unchanged.

Before correction, every non-target/nonpunisher target-race decision consumed a
tie variate, including competing owners. After correction, owners and active
punishers consume none; only neutral gamma decisions do. Common random numbers
remain deterministic and meaningful, but paths and subsequent tie-stream
alignment can diverge state-dependently. Artificial draw consumption was not
added.

All pre-fix conditional environments containing a target race are potentially
affected. Since compact checkpoints do not retain enough per-event ownership
information to prove an environment unaffected, the corrected Stage B sweep
uses a new output directory and cache model version
`race-owner-precedence-v2`; no old checkpoint is eligible for reuse.
