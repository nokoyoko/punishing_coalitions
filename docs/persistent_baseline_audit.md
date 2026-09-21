# Persistent baseline invariance audit

This is the preserved **historical v1** audit. The separate
[common persistent network v2 correction](persistent_network_v2.md) now implements
and tests common H/S0 semantics; the v1 findings and evidence below are unchanged.

**Finding: BASELINE MODEL CORRECTION REQUIRED.** Both H and S0 currently differ
across persistent rule labels at fixed population and integer seed. There are two
independent causes: rule-specific RNG initialization in all three models, and a
different S0 natural-fork transition in selfish-counter. This is avoidable.
The previous caveat describing it as a cross-rule limitation was insufficient:
it violates the requested common-baseline research design.

This audit adds tests and evidence, without changing engine logic, existing
tests, model versions, configuration, cache validation or historical results.
The evidence is in [persistent_baseline_audit_evidence.json](persistent_baseline_audit_evidence.json);
the executable reproductions are in
[test_persistent_baseline_audit.py](../tests/test_persistent_baseline_audit.py).
Only tiny local runs and scripted fixtures were used. No production simulation,
benchmark, SSH, `/xtra` access or remote job was performed.

## Matched-seed reproduction

The completed-run matrix uses target power 0.2, c1=0.1, c2=0.1, residual=0.6,
gamma=0.5, base seed=701, repetition=0, accepted-height target=40, unflagged and
empty active coalition. For each of H/S0 and lambda 0/0.005/0.02, it compares
counter-fork k=1, ignore and selfish-counter. There are 18 native completed runs
and 18 diagnostic completed runs with all three streams aligned to counter-fork's
initial RNG states. Aligned controls are explicitly labeled; they are not native
checkpoint data and were not placed in simulation caches.

The audit captures each discovery, the full block ledger, publication order and
attributes, natural-fork blocks/pairs, private and abandoned chains, atomic release
batches, public/leading frontiers, canonical chain, observed rewards and RNG draw
counts/state hashes after every discovery. Raw trace envelopes contain different
policy metadata and shapes, so comparisons normalize those envelopes into common
behavioral fields. Actual block ownership, ancestry, release order and pending
visibility state are not normalized away. Different termination events are
reported separately, not mislabeled as a changed empty private chain or a natural
fork. The evidence JSON records all final reward vectors and first differences by
field, plus source hashes for the engine files.

For **both H and S0, at each of the three lambda values**, native runs first differ
as follows:

| Pair | RNG state first differs | First discovery/behavior mismatch |
| --- | --- | --- |
| counter_fork / ignore | initialization, event 0 | event 1: c1 / residual |
| counter_fork / selfish | initialization, event 0 | event 1: c1 / residual |
| ignore / selfish | initialization, event 0 | event 2: target / residual |

All pairs already draw different random numbers at event 1. Ignore and selfish
happen to map their first discovery draws to the same residual actor. These event
numbers are for the specified fixture, not a claim about every seed.

Final canonical reward vectors below are ordered `(target, c1, c2, residual)`:

| Baseline | lambda | counter_fork | ignore | selfish |
| --- | --- | --- | --- | --- |
| H | 0 and 0.005 | (5,4,2,29) | (7,7,8,18) | (8,3,4,25) |
| H | 0.02 | (5,4,2,29) | (6,7,8,19) | (8,3,4,25) |
| S0 | 0, 0.005 and 0.02 | (3,5,2,30) | (3,7,9,21) | (6,3,4,27) |

Aligned-stream controls isolate transitions from namespace differences:

* Counter-fork and ignore match in every compared field for H and S0 at all three
  lambda values. Their unflagged mining path is the same.
* H matches across all three models, including RNG consumption. Additional
  seed-84 scripted H fixtures actually open/consume natural-fork windows at 0.005
  and 0.02 and still match. Seed 701 alone sees no aligned H natural fork in these
  short runs, so that negative observation is not the only evidence.
* The aligned seed-701 S0 controls also happen to match: they never exercise the
  disputed long-private-lead transition. This does **not** establish general S0
  equivalence. The five-discovery counterexample below exercises it directly.

## The first semantic divergence, independent of namespace

Keep the same population and gamma, use seed=84 and repetition=0, align all three
streams, and supply the identical discoverer schedule:

`target, target, target, honest_residual, c1`.

This is a scripted unit sequence, not a stochastic efficacy estimate. Forced
discoverers consume no discovery RNG. Tie and natural-window draws use actual
seeded counter-fork streams; no successful natural-window draw is fabricated.
The first natural draw is **0.00027760641597729396**; the first tie draw is
**0.4448503697700287**.

| Event | Common state or divergence |
| --- | --- |
| 1–3 | Target withholds T1→T2→T3, block IDs 1,2,3; public tree is empty. |
| 4, before window decision | Residual publishes H1, ID 4, from genesis. All models release T1, ID 1. Publication order is `[4,1]`; private suffix is `[2,3]`; reference is H1. |
| 4, window decision | Counter-fork/ignore consume zero natural draws and leave no window. Selfish consumes one draw; at lambda 0.005/0.02 it delays bundle `[4,1]`. |
| 5, counter-fork/ignore | c1 sees H1/T1, consumes the tie draw and extends T1 (parent 1). The target then releases `[2,3]` atomically at discovery event 5. Publication order becomes `[4,1,5,2,3]`; canonical chain is `[1,2,3]`; target has three rewards. |
| 5, selfish | c1 sees neither delayed tip, mines from genesis (parent null), and creates natural block 5 without a tie draw. The target retains `[2,3]`. Publication order is `[4,1,5]`; reference remains `[4]`; residual has one reward. |

Thus for lambda **0.005 and 0.02**, the first semantic state mismatch is **event
4** (pending window and RNG), and the first parent/publication/private-chain/
frontier/canonical/reward mismatch is **event 5**. Both counter-fork/ignore versus
selfish exhibit it; counter-fork versus ignore remains identical.

At **lambda 0**, event 4 still consumes the extra natural draw in selfish-counter,
but it cannot open a window. All physical mining fields match through the fixture;
the natural RNG state/count does not. Because the natural stream is separate and
all lambda-zero opening tests fail, this extra draw alone does not change
lambda-zero rewards under aligned discovery/tie streams. It nevertheless violates
the requested RNG-consumption invariant and can shift later draws at positive
lambda even when the first extra draw does not open a window.

The five-event reward comparison is a prefix observation at different attained
heights, not a comparison of estimates at a common completed horizon. The native
completed-horizon reward results are reported separately above.

## Exact code causes

1. [`PersistentSimulation._rng`](../punishment_sim/persistent.py#L218), lines 218–220,
   hashes `model_version:seed:stream_name`. Model version depends on punishment
   rule even when unflagged. Constructor lines 214–216 create discovery, tie and
   natural streams this way. No separate policy RNG is needed for this defect:
   the baseline streams themselves are namespaced by punishment.
2. [`PersistentSimulation.step`](../punishment_sim/persistent.py#L396), lines
   396–398, dispatches every `SelfishCounterSpec` run to `self.policy.step`, with
   no inactive-punishment exception. The new policy also contains baseline target
   and network evolution; it is not merely a punishment hook.
3. The earlier [`step` opening guard](../punishment_sim/persistent.py#L432), lines
   432–436, runs after target response but requires `not had_private`, `not
   had_tie`, no prior window, and `longest_tips == {bid}`. A public discovery at
   positive target private lead therefore cannot open a delay window.
4. [`SelfishCounterPolicy.step`](../punishment_sim/selfish_counter.py#L209), lines
   209–219, instead permits a window if private work remains after reactions. It
   requires the discovered block to have advanced height, not to remain the
   unique highest tip. It consumes a natural draw and stores the *entire* new
   publication bundle, even after a partial release has created a public tie.
   This is the first state-transition mismatch in the scripted case.
5. [`SelfishCounterPolicy._honest_parent`](../punishment_sim/selfish_counter.py#L152),
   lines 152–175, removes the bundle from the next honest miner's view (except its
   known own blocks/ancestors). The earlier path removes at most one pending
   block. This creates the event-5 parent/tie-draw mismatch.

The shared [`release_plan`](../punishment_sim/selfish_strategy.py#L15) is not the
initial cause: both release T1 at event 4. Neither atomicity, discovery count nor
release ordering differs at that point. Selfish reaction rounds have only the
target participating in S0. The later full-release difference follows from the
different honest parent choice/public height. Gamma and residual ownership are
the same shared fork-choice code, not an extra coalition influence parameter.

## Pending windows and atomic batches

These implementations store a reduced next-discovery *visibility mask*, not an
asynchronous network delivery queue. Every public block becomes global public
information immediately for strategy/policy reactions; the mask affects the next
ordinary honest discovery. Selfish target discoveries use the full public view.

| Transition | Earlier counter-fork / ignore | Current selfish-counter |
| --- | --- | --- |
| Honest advancement against private lead 1 | Release one block into a tie; no new window/draw | Same; private suffix is exhausted |
| Honest advancement against private lead 2 | Atomic two-block overtake; no new window/draw | Same; private suffix is exhausted |
| Honest advancement against private lead >2, initially no tie/window | Release prefix, retain suffix; no new window/draw | One opening draw after reactions; successful window includes honest block and released prefix |
| Already-open window, next discovery privately extends target | Window is consumed by that real discovery | Same; no natural fork is created inside private history |
| Existing bundle, next discoverer knows its own honest tip and extends it | No corresponding long-lead bundle in the earlier path | Old window is consumed; ensuing full target release is atomic, with no redraw or renewed window |
| Later ordinary advancement after full release has settled | Can open a new one-block window | Same in this isolated single-target case |

In neither path does publishing multiple blocks insert mining opportunities or
pause a window for multiple discoveries. Both consume the old window at the
start of a real `step`, even if its discovery is private. New selfish windows
are sampled **after** the complete immediate release cascade; they are not an old
window surviving that cascade. A pending window used at the start of a step is
not replenished by a release in that same step. The tests cover this explicitly
with the schedule `T,T,T,c1,c1`: c1 knows its own block 4, extends it at event 5,
and the target releases `[2,3]` atomically, with no extra window or discovery.

Selfish-counter can therefore insert a natural third sibling before resolving a
selfish tie, whereas the older path forces the next honest miner to choose a
known tip. Conversely, the new mask can suppress the *immediate* ordinary tie draw
by hiding both tips. These are actual changed mining opportunities/views, not just
different log formatting.

## Scientific judgment and intended correction

**The baseline invariance requirement is correct and achievable.** Punishment
being disabled supplies no scientific reason to change target strategy, network
law, fork choice or RNG coupling. The split is not unavoidable.

The RNG namespaces in all current models are incompatible with the specified
same-seed trace invariant. H's observed differences are sampling/coupling
differences, not evidence of a different H transition law or a biased expected H
payoff. The selfish-counter S0 mismatch goes further: it changes the conditional
transition law after the same public/private history, with probability lambda.

The **new implementation is wrong as a supposedly interchangeable punishment
model**: inactive punishment selects a different network process. Its coexistence
extension should have been proposed as a shared baseline change, not attached to
one punishment label. The previous lambda-zero equivalence tests checked blocks
and rewards but not natural RNG consumption; the audit fills that gap.

The **earlier engine also has a restrictive modeling limitation**: a hidden target
lead makes benign propagation delay impossible for an otherwise public discovery.
No physically necessary property of standard selfish mining makes honest network
latency vanish because unpublished work exists. Under the intended model allowing
natural forks alongside private chains, this exclusion is inadequate and needs
correction. It was a documented reduced-model convention, not evidence of a
different Eyal–Sirer release strategy or a historical reward-accounting bug.

Simply declaring the new network path scientifically correct would also be wrong.
Its opening condition still depends on whether *any* private suffix survives:
lead-one and lead-two releases cannot open windows, while longer leads can. That
restriction is not justified by the supplied physical assumptions. With multiple
members, it can even depend on an unrelated member retaining hidden work.

The intended common network contract should be:

* One versioned public propagation process for all rules and all conditions.
  Eligibility must depend on declared public/visibility events, not the selected
  punishment rule or knowledge of hidden suffixes. Private discoveries alone
  create no public propagation opportunity.
* One real discovery per step. Finish each release atomically in actual
  parent-before-child order; immediate reactions add publications, not discoveries.
* If retaining the existing one-discovery approximation, use one well-defined
  public announcement episode per eligible discovery/reaction event, with one
  opening draw. A concrete minimal proposal retains the public guards: no incoming
  window, no leading tie at the start, and a discovered public block advancing the
  pre-step maximum. After all immediate reactions, draw once and, if successful,
  delay the resulting announcement bundle together for the next ordinary honest
  discovery, retaining explicit publisher knowledge, target-tip gamma and residual
  neutrality. Remove both private-state guards: do not suppress the episode merely
  because a private chain exists or has just been exhausted. This includes the
  lead-one tie and lead-two overtake cases that both current paths exclude.
* Consume an existing episode on its next real discovery, with no per-block redraw,
  fictitious discovery, finalization release or arbitrary postponement by a batch.
  Document the strategic target's existing full-public-view assumption explicitly.

The bundle choice is a **proposed reduced-model convention**, not a uniquely
derivable network-latency law. The prompt does not specify per-message arrival
times, recipients or correlated delays within a release. Such details would be
needed to choose a richer network model or prove that a numerical lambda has the
same calibration for single-block and multi-block announcements. This uncertainty
does not weaken the common-baseline requirement. Do not silently replace v1 with
either existing path or pretend the newer predicate is a complete network fix.

## Required architecture, versions and provenance

No runtime correction was applied during this audit. The required follow-up is:

1. Separate common target/mining/network evolution from punishment. H/S0 use the
   same engine path and no active punishment policy, regardless of the consuming
   study's rule. Selfish actor storage/release machinery is generic engine state;
   flagged selfish punishment only selects additional actors for that strategy.
2. Give common discovery/tie/natural streams a baseline-engine namespace without
   punishment. Use the same namespace for baseline **and flagged** conditions to
   preserve within-rule CRN. Changing namespaces only in H/S0 would break the
   existing H/SC and S0/SC discovery pairing. Any genuinely policy-specific random
   choices must use separate streams and cannot advance the common streams.
3. Put the agreed propagation episode logic in that common engine, including
   flagged runs. Routing only H/S0 to older code would repair a narrow equality
   assertion while retaining network-treatment confounding between H/S0 and SC.
4. Introduce a canonical baseline identity/schema, for example
   `persistent-common-baseline-v1`, plus new counter-fork/ignore/selfish-counter
   semantic versions (e.g. each `-v2`). All three model versions need changes:
   even unchanged lambda-zero transitions acquire different deterministic RNG
   provenance. Positive-lambda network changes also affect HF, SC and leaveouts,
   not just H/S0. Update task IDs, manifests, checkpoint schemas, validators,
   outputs and analysis grouping accordingly.
5. Preserve all existing v1 results, schemas and fixtures, and historical petty
   files. Add new canonical baseline fixtures; do not overwrite old hashes or
   reinterpret old checkpoints as having the corrected semantics. No migration
   or new identifier is installed by this audit.

The minimal compatibility alternative would route inactive selfish-counter runs
through the older baseline and fix common RNG initialization. That is not enough
for the intended common-network comparison unless flagged runs also use the same
declared network semantics. It also retains the earlier private-lead propagation
restriction. The recommended correction is the common-engine design above.

H/S0 **cannot currently be safely reused by dropping the rule from the key**.
[`mining_cache_key`](../punishment_sim/persistent.py#L59) includes model/rule/k;
[`validate_run`](../punishment_sim/persistent_checkpoint.py#L41) checks those
identities and population/seed/condition provenance. Those guards remain intact.
Even H and counter-fork/ignore S0, whose transition laws match under aligned
streams, do not have identical native RNG provenance. Distributional equality is
not permission to relabel a seed-specific sample.

After correction, a shared baseline cache can omit punishment rule and k if its
key retains the canonical baseline/target/network/fork-choice/accounting/RNG
versions, full ordered population with identities and powers, gamma, lambda,
actual repetition seed, target strategy, horizon and relevant observation/resource
semantics. Only complete unpunished conditions qualify. Store baseline results
under their own immutable schema/digest and preserve actual seed/stream provenance;
rule-specific study manifests reference that digest, rather than forging the
baseline's model label. Validate the baseline ledger and each consumer's requested
environment. Flagged runs retain rule-specific identity. Any historical import
would need a separate explicit provenance-preserving validator and migration.

## Effect on the research comparisons

Writing rule-indexed baselines exposes the confounding:

`D_P - D_R = (H_P - H_R) - (SC_P - SC_R)`.

Current H namespace differences add finite-sample noise and lose cross-rule
coupling; they do not by themselves prove a systematic mean bias. But different
flagged network semantics can still contaminate a punishment interpretation of D.

`B_P - B_R = (SC_P - SC_R) - (S0_P - S0_R)`.

Here selfish-counter's changed S0 network law can change the expected reference
payoff itself. Apparent differences in member credibility can contain baseline
network effects as well as retaliation effects. This audit establishes the
mechanism, not its magnitude or sign in a research sweep.

Q has no explicit H/S0 term when the leaveout remains nonempty. Repairing the
baseline alone therefore does not make Q comparable across differing network
engines. Moreover the current private-survival window predicate can respond to
which selfish member was omitted. For a singleton coalition, the leaveout becomes
S0, so a baseline-versus-flagged path split directly enters Q. A common propagation
law should let changed public behavior affect delays, without an extra hidden-state
or rule-label gate.

## Tests and acceptance gates

The new audit module has **48 passing checks and 9 explicit expected failures**.
The failures are assertions of native H/S0 equality at the three requested rates
(six cases), and aligned long-lead S0 state/RNG equality at those rates (three
cases). They are strict and only accept `AssertionError`; unrelated errors remain
failures. These are known missing v1 invariants, not nine successful alignment
checks. Existing tests have not been weakened or edited.

Validation on 2026-09-16: the complete local suite,
`.venv/bin/python -m pytest -q`, finished with **683 passed, 9 xfailed in 47.81s**.
All 635 previously existing tests passed. `git diff --check` and separate no-index
whitespace checks for the new/untracked audit files passed. Hashes of all eight
persistent runtime modules still match the recorded evidence; tracked files have
no diff. The changes for this audit are this report, its evidence JSON, the new
audit test module, and a short audit link/status note in the selfish-counter doc.

Passing checks cover native divergence locations; aligned counter-fork/ignore
equivalence; aligned H including real natural forks; lead 1/2/3/12 release
atomicity; one-block and multi-block release; windows before a private discovery,
after a release, and during retained target private state; window consumption
without a public discovery; release during consumption of an existing window;
unflagged nonempty candidate lists; and rejection of cross-model baseline cache
payloads. Instrumentation records every common stream's count and state.

For new canonical versions, the acceptance tests must require equality without
manually aligning streams or accepting expected failures: H and S0 at lambda
0/0.005/0.02, multiple seeds/repetitions and populations, including all scripted
edge cases above; unchanged owner/gamma behavior and no fictitious discoveries;
common discovery streams in flagged and baseline conditions; no inactive-policy
calls that affect randomness; baseline cache hits across consumers; rejection of
wrong environment/seed/network/version/provenance; identical resumed versus fresh
baseline traces. Preserve the existing v1 regression fixtures separately.

BASELINE MODEL CORRECTION REQUIRED
