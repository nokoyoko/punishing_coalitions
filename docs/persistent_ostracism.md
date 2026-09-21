# Persistent ostracism

The new semantic model is **`persistent-ignore-v1`**, selected by
`punishment_rule="ignore"`. It reuses `PersistentSimulation`; it does not duplicate
the persistent engine or modify the historical v4 petty engine. Independent
selfish counter-mining is documented separately in
[persistent_selfish_counter.md](persistent_selfish_counter.md). Combinations of
punishment rules remain unsupported.

The counter-fork model remains `persistent-counter-fork-v1`, with the same
`PunishmentSpec`, RNG namespace, rules, configuration/task/cache identities,
checkpoint schema and result shapes. `OstracismSpec` is separate, so the existing
counter-fork constructor still rejects `ignore`. Both specifications are accepted
by the shared engine and research interface. No production configuration or k
grid is added or changed.

## Architecture

`punishment_sim/ostracism.py` contains the new specification and `OstracismPolicy`.
The policy implements the same eligibility, publication-notification, active-state
and observation interface as counter-fork. The shared engine still owns every
discovery, private block, public branch, publication batch, canonical adoption,
reward reversal and payoff observation. Parents are assigned on discovery and
never changed by the engine. The policy assigns no rewards and creates no blocks.

The shared modules now dispatch model/RNG identity, policy construction, native
checkpoint schema and terminal diagnostics by rule. Counter-fork dispatch produces
its previous values. Ostracism publication provenance and eligibility are
independently reconstructed by the checkpoint validator from the raw block ledger.

Every coalition member retains an individual identity, hash power, parent choice
and reward account. One public rejected-root ledger is sufficient within a
conditional run because all active members have the same persistent flag and
observe the same atomic announcements. This is not a pooled mining actor or a
shared private chain. Each conditional/leaveout run constructs a separate ledger
and a separate block tree; no state is copied from a full-coalition run.

## Activation boundary and rejected ancestry

For an ordinary conditional study, the flag and active coalition are fixed at
construction. The policy is armed iff the flag is true and the active coalition
is nonempty. A flagged nonempty run attaches at genesis, so the activation
boundary is **publication sequence zero**, before its first publication.
Unflagged and empty-coalition runs have no activation boundary and reject nothing.

The policy attachment primitive also works on an existing tree: it records the
current publication sequence and treats all existing public history as acceptable.
This supports deterministic grandfathering tests. A previously discovered private
target block is not grandfathered if it is first published after attachment.
Nonzero-boundary attachments are not a new experiment dimension: standard flagged
study checkpoints require the genesis boundary and reject such fixture histories.

After attachment, **every newly published target block** becomes an offending
root, including stale target publications and publications within already rejected
ancestry. Ostracism has no counter-fork-style longest-tip relevance filter. A
lower stale publication may have no immediate behavioral effect, but its branch
remains unacceptable if it later returns to relevance.

The policy stores:

* `rejected_roots`: all offending target block IDs, retained permanently.
* `minimal_rejected_roots`: offending roots with no previously rejected ancestor.
* `rejected_by`: the first minimal rejected ancestor of each rejected public block.
* Eligible public frontier nodes, the best eligible height/tips, and the rejected
  roots currently represented at the global leading public frontier.

For each publication in parent-before-child order, inherit the parent's first
rejected root. A newly offending target block starts a new minimal root only when
its parent has no rejected ancestor. Thus `A->T1->H1->T2` remains rejected from T1;
T2 is recorded as an offending publication but never moves the acceptable boundary
past T1. A target publication on a different acceptable branch starts a new minimal
root. Honest ownership of descendants never repairs rejected ancestry.

All blocks in a release become public atomically before fork-choice opportunities
resume. Rejection provenance follows their actual publication order. A target
batch `T1,T2,T3` records all three roots, retains T1 as the first rejected ancestor,
and does not offer coalition discoveries between releases. Duplicate publication
observations change nothing.

## Persistent state and fork choice

There is **no k, timeout, random capitulation or runtime-dependent policy change**.
`counter_fork_k` is null in the common metadata shape for ignore; providing a
non-null value is an error. Root sets only grow. No depth deficit makes a rejected
descendant eligible, and no root is erased when its branch becomes noncanonical.

Eligibility applies to active members whenever the policy is armed, regardless
of whether an immediate conflict is currently leading. The policy's `active`
diagnostic means at least one globally leading public branch has rejected ancestry;
it does not control whether stored rejections are enforced. A strict overtake by
acceptable branches can end that immediate conflict while the policy remains armed.
Old rejected branches can reopen conflicts without another target publication.
Multiple roots and simultaneous conflicts are represented independently.

Active members first filter by rejected ancestry and the existing reduced
visibility window. The best eligible nodes can be interior public prefixes,
not just leaves of the network's public tree. For example, when the only public
chain is `A->T->H`, A remains an eligible mining parent. Genesis is the fallback
only when no post-genesis public block is eligible.

Among maximum-height eligible nodes, ordinary persistent-engine choice applies:

1. Explicit ownership keeps the miner on its own eligible competing tip.
2. Without an eligible owned tip, target-absent ties use uniform neutral support.
3. A single eligible target-owned competing tip gets gamma, and other tips share
   the remainder. In ordinary genesis-activated ostracism, newly target-owned tips
   are rejected before this calculation. An attachment fixture can legitimately
   have a grandfathered target-owned tip; gamma may apply to that eligible tip.

Neither ownership nor gamma overrides eligibility. Target ancestry alone never
grants gamma. Oceanic residual discoveries receive no persistent ownership privilege.

Nonparticipating candidates, including omitted leaveout members, the residual,
and the target continue the existing ordinary/selfish behavior. They can extend
rejected branches. The target's private-chain strategy and public release rules
are unchanged from the persistent foundation.

## Natural forks

The engine retains its reduced lambda propagation model: a single new globally
leading publication can open a one-discovery visibility window when no prior
window, target private lead or existing leading tie is being processed. This is
not a full network-delay model, and windows are not independently opened on each
lower coalition branch.

Natural forks can occur between acceptable branches, between acceptable and
rejected branches, and on the network's rejected branch while the coalition is
far behind. They can also occur among acceptable branches after an old rejected
branch has ceased leading. Retaining old roots does not suppress these windows.

An active member's work while a rejected branch leads is tagged `ignore`; it is
not counted as a natural sibling merely because a propagation window also exists.
A neutral delayed sibling is tagged `natural_fork`. With no leading rejected
conflict, members can participate in ordinary acceptable natural races. Natural
pair counters and discovery accounting remain separate from intentional punishment.

## Detector, payoff and statistical analysis

The existing H, S0, HF(C), SC(C) and SC(C minus j) architecture remains intact.
False-positive honest targets are ostracized on publication. A missed selfish
target is never ostracized. An omitted member remains an explicit neutral miner
at exactly its original hash power; it is not removed from the population.

The new RNG namespace is `persistent-ignore-v1`; within a repetition, conditional
runs share the existing `base_seed + repetition` seed schedule and named discovery,
tie and natural-window streams. Separate conditions evolve independently, and
different repetitions use distinct seeds. Cache identity includes model and rule,
even for H and S0, so counter-fork behavior caches are not reused for ignore.

The fail-closed statistical adapter still uses the unchanged paired calculations:
`D=H-SC`, `B=SC-S0`, `Q=SC-SC_without_j`, means, sample standard deviations, standard
errors, paired 95% intervals, variance diagnostics, supported/refuted/inconclusive
statuses, weak/strict joint-feasibility distinctions, detector mixtures and
false-positive costs. Continuous TPR ratios retain their paired bootstrap. No
large negative participation cost is clipped, reclassified or exempted.

The runner defaults remain 20 repetitions and 30,000 reference-chain blocks;
tests supply small explicit overrides. No production design is defined here.

## Finite horizon and unresolved boundaries

Observation uses the reference chain after the first completed discovery step
reaching the target height. Normal atomic publication responses may overshoot the
target. The engine does not wait for ostracism to become inactive, mine extra
settlement blocks, release private work, or force a change of strategy.

Canonical membership determines the current rewards. The full canonical ledger,
all public/private leaves, divergent paths, publication provenance, abandoned
private work and pending visibility state remain recorded. Ostracism adds:

* Armed state, activation boundary, all roots, minimal roots and leading conflicts.
* Rejected public leaves and the complete eligible frontier, including eligible
  interior prefixes that have no competing child yet.
* The first rejected public ancestor for each alternative, including hidden
  descendants of already rejected public roots. This describes eligibility by
  *already published* ancestry; an unpublished target block can itself become a
  new root upon a future release.
* Whether the reference chain is rejected, the best eligible height, and the
  reference-minus-eligible height deficit.
* Exposure of canonical suffixes above eligible prefixes as well as above existing
  alternative branches' common ancestors. This avoids falsely reporting zero
  exposure when the coalition has not yet found its first competing block.

The method is **`ostracism-complete-frontier-conservative-v1`**. Any remaining
alternative, leading rejected conflict or pending visibility window marks the
endpoint potentially material. Unresolved per-actor payoff bounds remain `[0,1]`.
These broad bounds are not statistical confidence intervals, and no private-lead
omission formula is applied to deep public forks. Historical stale branches can
make the bound persistently uninformative. Absence of a flag is not a proof of
future finality. Reported sampling CIs describe the finite-horizon observations,
not an eventual settled-chain payoff.

Resource exhaustion remains `INCOMPLETE_RESOURCE_LIMIT`, with the policy, roots,
frontiers and observed rewards preserved. Incomplete or unsupported runs cannot
enter completed statistical repetitions or native completed checkpoints.

## Identity, artifacts and compatibility

Ignore model/rule identity appears in mining keys, configuration/task IDs, RNG
namespaces, checkpoints, result metadata, every CSV family and analysis groups.
The native schema is **`persistent-ignore-conditional-checkpoint-v1`**. It does not
accept counter-fork or v4 checkpoints. In addition to the common complete-ledger
and seed validation, loading independently reconstructs rejected ancestry, eligible
frontiers, activation history, conflicts, deficits and conservative bounds. It
rejects a supposedly active member mining on rejected ancestry in a standard
genesis-activated conditional run. Missing or invalid data never silently triggers
replacement mining in analysis-only mode.

The same explicit local entry point, `python -m punishment_sim.persistent_sweep`,
accepts a supplied ignore configuration with
`expected_model_version="persistent-ignore-v1"` and `punishment_rule="ignore"`.
No production configuration or launch command is supplied. Analysis-only and
dry-run behavior are unchanged. Output-directory guards prevent mixing designs.

Before shared-code edits, small counter-fork fixtures captured 12 full seeded
results/traces plus all 10 files from a tiny local runner case. Tests compare
their hashes byte for byte, covering identities, manifests, checkpoint schemas,
raw checkpoint data, CSVs and JSON analysis. These tests supplement, rather than
modify, the existing counter-fork and historical v4 regression suites.

## Multiple-target-tip reachability audit

**UNREACHABLE UNDER NORMAL EXECUTION.** The counter-fork rejection guard is retained
unchanged. This conclusion concerns `PersistentSimulation.step()` and its current
honest/selfish target strategy, not arbitrary scripted `discover`/`publish` calls.

The invariant is stronger than the guard: **successive target discoveries have
strictly increasing heights**, including unpublished and abandoned discoveries.
Consequently at most one target-owned block exists at any height. Competing tips
passed to the publication guard or actor fork choice are equal-height nodes, so
they cannot contain two target-owned tips.

Inductive argument:

* Public maximum height never decreases: publication only adds blocks; reference
  adoption selects a public maximum. Counter-fork policy reactions do not delete
  blocks or change heights.
* An honest target normally discovers above the visible maximum. In the only
  delayed-view case, the pending non-target block was a **unique** new public
  maximum when the immediately preceding step ended. No earlier published target
  block can already occupy that height; otherwise the pending block could not
  have been the unique maximum. Mining its parent therefore still gives a target
  block higher than every preceding target discovery. When the target itself
  owns the pending block, explicit first-publisher ownership lets it extend that
  block instead of creating another target sibling. Honest mode has no private
  target discoveries in normal execution.
* A selfish target with a private suffix extends its last private block, increasing
  its own height. Partial releases retain the suffix ending at that same latest
  target discovery. If the suffix is fully published, the public maximum reaches
  at least that last discovery's height. If it is abandoned, the rival public
  height is strictly greater than the private tip's height. In either empty-private
  case, the next target discovery builds above the public maximum. The selfish
  target does not take the reduced delayed-view sibling path. Thus its next
  discovery is strictly higher even after abandonment or release.

These cases cover all target discovery transitions. Publication itself creates
no additional blocks. Coalition choices, k, gamma and lambda do not break the
height argument. The proof also covers policy-filtered candidate sets, since
uniqueness holds across the entire ledger, not just current public leaves.

Bounded tests corroborate the invariant for all 243 length-five discoverer
schedules in a three-actor population, across k=1/2/3, honest/selfish strategies
and three lambda/gamma settings: 4,374 small schedules in total. They check target
height growth and every actor's eligible tips. Finite exploration is not the
proof. Existing low-level scripted tests intentionally manufacture duplicate
target heights and still verify rejection. Future target strategies or external
state import would require a fresh reachability audit.

Multiple **rejected roots** do not imply multiple equal-height target-owned tips:
roots may be at different heights or have honest-owned descendants as their
current tips. Ostracism fully supports those concurrent histories.

## Performance and next work

No production benchmark has been run. Qualitatively:

* Trees, private archives, rejected roots and histories are retained without
  pruning. Memory therefore grows with discoveries until the observation/resource
  limit; there is no fixed branch-memory bound.
* Rejected ancestry propagates once per publication using the parent's cached
  first rejected root. Choosing an eligible mining parent examines best eligible
  tips and their one-step visibility fallbacks, not every root or every ancestor.
  A deterministic test forbids ancestry walking during this choice.
* The inherited publication path still scans the public leaf frontier. Many stale
  leaves can produce quadratic total work over a long run. Deep terminal path
  reconstruction across many overlapping branches can also repeat ancestry work.
  Full ledgers make checkpoints and repetition exports large. Full tracing copies
  growing policy snapshots per discovery and can itself be quadratic; production
  tracing is off by default.
* Before a future production sweep, consider indexed public height frontiers,
  ancestry/LCA indexing and deduplicated immutable block storage in exports.
  Rejected ancestry cannot simply be pruned because a temporarily orphaned branch
  may become competitive again. Optimizations need the same semantic regressions.

No new modeling decision is needed to use the requested ostracism rule under these
documented activation and propagation conventions. Broad production calibration
and scale validation are still outside this local implementation.

The separate selfish-counter model now provides per-member private storage and
independently evolving state machines, with explicit release-event ordering.
Its documentation distinguishes the new natural-fork delay extension from the
unchanged ostracism propagation convention. It adds no pooled private chain or
combinations of punishment rules.
