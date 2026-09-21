# Independent selfish counter-mining

The subsequent [baseline invariance audit](persistent_baseline_audit.md) found
that current v1 models violate common H/S0 requirements through RNG namespaces
and the S0 propagation split described below. The separate
[common persistent network v2 correction](persistent_network_v2.md) implements
the required shared network law. This document describes historical v1, whose
runtime semantics remain intact; its split is unsuitable for a controlled
cross-rule experiment.

The individual rule `punishment_rule="selfish"` selects
**`persistent-selfish-counter-v1`**. It extends the shared persistent block-tree
engine with Model-A independent selfish actors. It adds no production parameter
grid and changes no historical v4 file, configuration, identifier or importer.
The existing counter-fork and ostracism policies retain their exact behavior.
Combinations of punishment rules remain unsupported.

## State, information and activation

`selfish_counter.py` defines `SelfishCounterSpec`, `SelfishState` and
`SelfishCounterPolicy`. Each selfish actor has its own ordered unpublished suffix,
fork base, tip, lead, published exposure, release history and abandoned archive.
The target has such a state exactly when its strategy is `selfish`. Each member
has one exactly when the persistent conditional detector flag is true and that
member belongs to the active coalition. Member activation occurs at discovery
event zero, before any target discovery or publication.

The shared engine's old target-only `private` list is unused by this model.
The authoritative store is `policy.states[actor_id].private_chain`. There is no
pooled coalition actor, power, hidden branch, release optimization or reward
transfer. Other actors' unpublished blocks are inaccessible as mining parents.
Only an actor's own unpublished tip may extend its existing private suffix;
a new suffix starts on public history. Leaving a coalition does not remove the
miner or its power from the population.

The event scheduler can enumerate states, but each release decision reads only
the public frontier/ancestry and that actor's private chain. Other actors' hidden
chain lengths, tips and decisions are not inputs. Publishing a block makes it
ordinary public information available to every state machine. Diagnostic output
records all states for audit; miners do not use that diagnostic information.

## Shared full strategy

`selfish_strategy.release_plan` is the existing persistent target's release rule
extracted without changing its decisions. Both the old target path and each new
selfish actor use it. There is no private-length cap, truncated semi-selfish
policy, optimal strategy or additional coalition strategy.

* An actor with a private suffix extends its own private tip on discovery.
* Without a private suffix, it uses ordinary persistent public fork choice. It
  withholds if there is no public leading tie; in an exposed leading tie it
  publishes a resolving block, exactly as the existing target does.
* A public response is relevant only when a newly published block is currently
  a maximum-height rival tip that is not an ancestor of the private tip.
  Let `gap = own_private_tip_height - rival_public_height` after publication.
  A negative gap abandons the suffix. Gap zero or one publishes the whole suffix.
  A larger gap publishes just its unpublished prefix through rival height.
  Thus the usual lead-one event makes a tie, lead two overtakes, and larger leads
  can release a prefix while retaining private work.

Heights and ancestry determine competition; a stored lead is not blindly reduced
for each publication. A lower stale branch cannot reduce the lead. A new rival at
the same maximum height can cause a relevant release, but another sibling at an
already exposed height creates no additional private prefix to publish. Members
may compete with each other and with the target without sharing hidden work.

Single-target equivalence tests compare every block, publication attribute,
canonical reward and private suffix against both prior persistent policies under
identical supplied discovery/tie streams at lambda zero. A separate owner-swapping
test matches one coalition selfish actor against the original target at gamma
0.5 in binary neutral races. All-honest H behavior is also matched with nonzero
lambda. **Nonzero-lambda single-selfish trajectories are not claimed identical
across models**, because of the explicit propagation extension below; the shared
release strategy itself is identical.

## Concurrent publication and reaction order

The convention identifier is
**`public-snapshot-rounds-population-order-v1`**.

1. Complete the discovered public block or released batch atomically, including
   canonical accounting. A release lists parents before descendants.
2. Every actor independently plans its reaction to the same public snapshot using
   only its own private suffix. Actors are enumerated in population order: target,
   then candidate declaration order. Residual miners have no selfish state.
3. Commit all plans in that order. Each plan is irrevocable for this round, even
   if an earlier plan in the same round makes its release stale. Later actors do
   not revise a decision using an earlier actor's simultaneous release.
4. Queue the resulting public releases, then evaluate the next common-snapshot
   round. Stop when no public reactions remain.

No discovery or random draw occurs between release blocks or reaction rounds.
Every nonempty round releases or abandons at least one active private block, so
the cascade terminates without an arbitrary reaction budget. Failure of this
progress invariant is an explicit unsupported state, never a successful result.
The reaction log records the discovery event, observed public block IDs, snapshot
publication sequence, public height and individual decisions.

Sequential commits retain the engine's existing sticky reference choice at equal
height and earliest-publication choice after an overtake. Population ordering can
therefore affect which tied branch is the *observed reference*, even though it
does not give a miner hidden information or an extra discovery. This is a defined
simulation convention, not a claim that real announcements have this ordering.

## Public choice and propagation

Ordinary public choice retains the persistent engine's ownership semantics.
An explicit actor owning an eligible maximum-height tip continues it. The oceanic
residual has no persistent ownership privilege. Otherwise, a single target-owned
competing tip gets gamma; each of the other `n-1` tips gets `(1-gamma)/(n-1)`.
Without a target-owned tip, support is uniform `1/n`. Older target ancestry does
not confer gamma. There is no `gamma_C` or per-member influence parameter.

The new reduced natural-fork convention is
**`one-discovery-publication-bundle-window-v1`**. A public discovery that advances
height may open a lambda-probability one-discovery delay when the step began
without a leading tie or pending delay. It can do so when there was no private
work at the start, or when private work remains after the public reaction cascade.
If a cascade completely settles previously private work, it opens no new window.
Withholding alone never opens a window.

The delayed bundle contains the ordinary discovered block and every publication
in its immediate reaction cascade, in publication order. The next ordinary honest
discovery uses the highest public tips visible without that bundle. An explicit
publisher still knows its own published blocks and their ancestors; residual
discoveries get no such privilege. A block discovered below a hidden leading tip
is tagged `natural_fork`, and records the delayed bundle and its earliest hidden
leading tip as the pair-counter attribution. This attribution does not imply
that there were only two branches. Intentional selfish releases have separate
publication kinds and never increment natural-fork counters. Unpublished blocks
never enter a delay bundle. A selfish actor extends its private tip or uses the
full public view, matching the existing target's discovery convention.

This permits a natural public sibling while the target, c1 and c2 all retain
independent private suffixes. It is still a reduced delay model, not a network
latency simulation. Earlier models keep their original single-block window, which
does not open during target private work. Consequently new-model S0 at nonzero
lambda can differ from earlier S0 even without active retaliation. A deterministic
test explicitly captures that difference. Cross-rule comparisons at nonzero
lambda must report this propagation difference; they do not isolate punishment
alone. Lambda-zero comparisons isolate the individual strategy differences.

## Conditional research and identities

H has no selfish actors. S0 has only a selfish target. HF(C) has an honest target
and independently selfish active members. SC(C) has the selfish target and those
members. In SC(C minus j), j remains explicit and honest at unchanged power, with
no private selfish state. Each condition constructs an independent block tree and
state dictionary. The label is fixed for the run; there is no per-block detector
redraw. TPR/FNR and FPR remain downstream algebraic dimensions.

The existing reducer preserves `D=H-SC`, each member's `B=SC-S0` and
`Q=SC-SC_without_j`, means, sample standard deviations, standard errors, paired
CRN differences, Student-t 95% intervals, supported/refuted/inconclusive statuses,
point classifications and weak/strict feasibility. Continuous TPR bootstrap and
false-positive/prior mixtures are unchanged. Negative member costs are retained.
Runner defaults remain **20 repetitions** and **30,000 reference-chain blocks**;
the tests use small explicit horizons. No follow-up experiment stages are added.

Model/rule identity is included in configuration/task/cache keys, named RNG
streams, manifests, results, CSV rows and analysis groups. `counter_fork_k` is
null for this rule; a non-null value is rejected. Within each repetition all
conditions use seed `base_seed + repetition`, with separate discovery, tie and
natural streams. The discovery streams align across conditions; conditional
branching can consume different numbers of tie/natural draws. Different models
use different RNG namespaces, so cross-rule estimates must not be described as
paired CRN estimates merely because their integer seed labels match.

The schema is **`persistent-selfish-counter-conditional-checkpoint-v1`**.
Native validation checks the full block ledger, seeds, condition, ownership,
canonical accounting and frontier coverage, then reconstructs each actor's private
suffix and release decisions from discovery order and public publication prefixes.
It verifies atomic release order, snapshot decisions, activation, exposure,
abandoned work, private leads, natural-event bundles and terminal bounds.
Checksums alone are not attestation of an external producer. Prior model payloads
or malformed native data are rejected, with no silent fallback mining. Resume
and analysis-only reuse completed conditional checkpoints, not a serialized
mid-discovery engine. Missing tasks fail in analysis-only mode.

The analysis layer groups `counter_fork`, `ignore` and `selfish` separately and
retains counter-fork k. It can emit comparative groups without pooling their
semantics. No historical checkpoint importer is added.

## Accounting and terminal observation

Rewards follow actual owners on the observed canonical chain. Reorganization
removes old suffix rewards and credits the new suffix once. Hidden work earns
nothing. No aggregate coalition payoff substitutes for individual credibility.

Observation follows the first completed discovery/reaction step reaching the
reference-height target; an atomic release can overshoot it. There is no extra
settlement discovery, final forced release, adoption or abandonment. Every public
and private frontier, canonical block, unrewarded archive, pending public delay,
private lead and per-actor exposure remains in the result.

The boundary method is **`multi-selfish-complete-frontier-conservative-v1`**.
Any alternative branch, pending delay or undrained reaction queue makes the
boundary potentially material. Unresolved actor payoff bounds are conservatively
`[0,1]`, separate from sampling confidence intervals. Permanently active strategy
alone does not constitute an unresolved fork. Stale branches can keep these bounds
broad; absence of a material flag is not a proof of future finality. Complete
checkpoints require the reaction queue to have drained.

## Regressions, unsupported states and scaling

Existing petty, counter-fork and ostracism tests are unchanged. Pre-change fixtures
check 12 complete counter-fork result/trace hashes and 18 ignore result/trace
hashes, plus all ten output/checkpoint files for each tiny prior-model runner.
New tests cover independent storage, growth/release at leads 1/2/3/12, finite
multi-actor reaction cascades, ownership/gamma, natural forks with private work,
reorganization, horizon observation, detector/leaveout algebra, cache separation,
checkpoint validation, CSV grouping and reproducibility.

Local validation on 2026-09-16: `.venv/bin/python -m pytest -q` passed all
**635 tests in 47.17 seconds** (506 existing and 129 new). `git diff --check`
passed, and separate no-index whitespace checks covered the untracked persistent
files. Original persistent test files were compared byte-for-byte with the
pre-change snapshot; `ostracism.py` was also identical, as were the counter-fork
policy/specification ASTs. Tracked historical files had no diff. No production
simulation, benchmark, SSH, `/xtra` access or remote job was performed.

Multiple equal-height target-owned public tips remain explicitly unsupported.
They are unreachable through the implemented normal step rules: selfish target
heights strictly increase while private, and release/abandonment makes public
height at least the last target height before a new suffix starts. For an honest
target, a delay hides only the preceding step's bundle; the prior public maximum
is at least every older target height, and any target discovery in the bundle is
known to its owner. The next target block therefore also has a greater height.
Publication creates no blocks. Exhaustive short four-actor schedules corroborate
this induction, while scripted duplicate-tip fixtures still exercise the guard.
External interventions or new target strategies need a fresh audit. Pooled hidden
chains, combinations and per-coalition gamma are rejected. Resource exhaustion
is incomplete, with retained state, and cannot enter completed statistics.

No production performance benchmark was run. Likely scaling concerns are:

* Up to `m+1` independent state machines react to each relevant public event.
  Cascades can require several rounds, bounded by outstanding private blocks.
* Full blocks, public leaves, private/abandoned work, release histories and reaction
  logs remain retained; memory grows with discoveries without a fixed fork cap.
* Publication and private bookkeeping scan frontier/suffix collections. Delayed
  honest views currently rebuild visible public leaves from the public set.
  Long runs with many delay windows or leaves can therefore require quadratic
  total work. Terminal alternative paths can repeatedly traverse shared ancestry.
* Checkpoints retain complete ledgers and per-actor provenance. Tracing copies
  growing state at every discovery and can itself be quadratic; it is off by
  default. Output volume and validation/reanalysis cost need measurement before
  any future production design, without discarding scientific state.

## First proposed cross-rule check (not launched)

Start with lambda zero, gamma 0.5, target power 0.2 and either one 0.2-power member
or two independent 0.1-power members. Compare counter-fork k=1, ignore and selfish
using 20 repetitions of a short 200-block reference horizon. Inspect individual
D/B/Q, false-positive costs, boundary diagnostics and accounting. Use each model's
own RNG namespace and do not label between-rule differences CRN-paired. Keep the
within-model conditional pairing. The tiny horizon is for mechanism validation,
not scientific efficacy or feasibility conclusions.

Separately exercise small nonzero-lambda fixtures for delayed publication bundles.
A scientifically controlled nonzero-lambda cross-rule production comparison would
need an explicitly agreed common propagation design under new semantic versions;
changing earlier identifiers to conceal that difference is not appropriate.
Reaction snapshot ordering and reduced delay scope are now explicit conventions;
their empirical sensitivity, calibration and eventual settled-payoff inference
remain future modeling work. No production grid or job accompanies this proposal.
