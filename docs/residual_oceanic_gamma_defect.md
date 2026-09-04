# Residual-oceanic gamma defect

In v2, `_choose_race_branch` applied competing-sibling ownership before gamma
to every stored actor. Because `honest_residual` is stored as one aggregate
label, a residual-produced competing block caused the entire residual mass to
support that branch deterministically. This incorrectly treated an oceanic
population as one persistent pool.

Minimal trace: target owns sibling A; sibling B is attributed to
`honest_residual`; the next discovery is also attributed to `honest_residual`.
V2 returns B with probability one (`OWN_COMPETING_BRANCH`). V3 treats the two
discoveries as potentially different miners within the ocean: it chooses A
with probability gamma and B with probability `1-gamma`, returning
`OCEANIC_GAMMA_TARGET` or `OCEANIC_GAMMA_COMPETING`.

Persistent explicit actors—the target and named candidates—retain ownership.
An active punisher owning neither sibling deterministically selects the
non-target branch. Neutral explicit miners and oceanic residual mass consume a
tie RNG draw; deterministic ownership and punishment choices do not.

Model/cache version is `race-owner-oceanic-residual-v3`. All v2 target-race
checkpoints are behaviorally stale. Common-random-number alignment changes
because oceanic decisions now consume gamma draws; obsolete draws are not
forced. Natural forks remain limited to represented distinct actors: no
residual-residual internal-fork mechanism or pool-size distribution is added.
