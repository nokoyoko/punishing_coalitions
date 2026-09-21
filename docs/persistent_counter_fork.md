# Persistent forks and counter-fork punishment

Implementation version: **`persistent-counter-fork-v1`**. This is a separate
scientific model, not a replacement for `race-owner-oceanic-all-races-v4`.
No production counter-fork configuration or production k grid is supplied.
The existing v4 configurations, engines, seeds, tests, CLI, task IDs, checkpoint
schemas, importers and output formats are unchanged.

## Architecture and entry points

| File | Responsibility |
| --- | --- |
| `punishment_sim/persistent.py` | Discovery, private storage, atomic publication, persistent public tree, policy reactions, fork choice, reversible canonical rewards and observation |
| `punishment_sim/persistent_study.py` | Independent conditional simulations; complete-cache adapter to existing paired statistical calculations |
| `punishment_sim/persistent_checkpoint.py` | Native schema, content digest, atomic writes, seed/condition/block-accounting validation |
| `punishment_sim/persistent_sweep.py` | Separate task identities, scope calculation, local execution/resume, analysis-only mode and CSV exports |
| `tests/test_persistent_counter_fork.py` | Scripted state transitions, ownership, natural forks, reorganization, horizon and small seeded runs |
| `tests/test_persistent_study.py` | Paired statistics, 20 repetitions, CRN provenance, isolation, checkpoint rejection and tiny runner fixtures |

`PersistentSimulation` owns the block ledger. A block records its parent, height,
individual owner, discovery sequence, initial withholding, publication sequence,
release batch, publication kind and current canonical membership. Publication
visibility is explicit: an unpublished block has no publication sequence.
Private and public branches coexist, with no two-branch or private-lead cap.
Coalition members always remain separate miners; there is no pooled hash power,
shared private chain or pooled reward account.

`ForkPolicy` selects eligible blocks, receives atomic publication notifications,
exposes active/armed state and supplies an observation snapshot. The counter-fork
policy never credits rewards. Canonical adoption finds the common ancestor,
reverses the removed suffix's individual rewards, then credits the added suffix.
Valid noncanonical blocks stay in the tree and can become canonical later.

The observer's reference chain is the highest public chain. At equal height it
retains its current tip when possible; otherwise it takes the earliest-published
highest tip. This deterministic accounting convention does not override miners'
individual fork choices. No finality or confirmation depth is implied.

## Exact counter-fork state machine

Construction requires `punishment_rule="counter_fork"` and a generic positive
integer `counter_fork_k`. Booleans, nonintegers, nonpositive values, other rules
and rule combinations are rejected. Tests use k=1, 2 and 3; a constructor check
also establishes that the implementation does not restrict k to that test set.

1. **Unarmed:** detector flag false or active coalition empty. Publications never
   activate punishment.
2. **Armed, idle:** wait for a newly public relevant target block T.
3. **Active:** set trigger=T, anchor=parent(T), defended high-water height=height(T),
   depth=0. Each active member mines a highest public descendant of the anchor
   that does not descend from T. The anchor itself is eligible as a fallback.
   Existing eligible branches are reused, including work by neutral miners.
4. **Defending advancement:** a newly published non-target descendant of T above
   the defended high-water height increases depth by the height increase. Two
   defending siblings at the same height consume one advancement in total.
   Counter-fork and unrelated blocks consume none. Target descendants that
   qualify for refresh are handled by the refresh rule instead.
5. **Refresh:** each newly published qualifying target block replaces the trigger
   and anchor and resets depth to zero. Previous trigger history can now be
   accepted. Record the prior episode as `REFRESHED`; remain active.
6. **Success:** the reference chain excludes T and its height is strictly greater
   than every public leaf descending from T. Record `SUCCEEDED` and return to
   armed idle. Equal height is never success, even if observer tie ordering happens
   to prefer an alternative.
7. **Deadline:** if success has not occurred and depth >= k, record `CAPITULATED`
   and return to ordinary fork choice, still armed. Delete no blocks.

Success is evaluated before the deadline for a complete publication batch. A
batch that both exhausts the budget and strictly overtakes the defending branch
therefore succeeds. This precedence has a scripted atomic-batch test.

**Relevance is public reachability:** in the complete post-batch public tree, a
newly published target block must be an ancestor (including itself) of at least
one globally maximum-height public tip. This is evaluated before actor-specific
punishment eligibility. A lower stale branch cannot trigger; a maximum-height
tie can. A target ancestor exposed with later blocks in the same batch can
qualify. Previously published blocks that later return to the reference chain do
not count as new publications. Duplicate publication observations are no-ops.

**Batch convention:** validate parent-before-child publication order, reject
ambiguous multiple target tips, then expose the entire release before reacting.
Process qualifying target blocks in actual publication order and record each
refresh, without mining or RNG draws between them. The last qualifying target
block becomes the current trigger. Count only defending height advances
published after that trigger; superseded triggers' counters cannot consume the
new trigger's budget. Success/deadline outcomes are evaluated on the complete
post-batch tree for the final trigger. A pure multi-block target release ends
with depth zero, anchored at the last target block's parent.

For k=1, `A->T` followed by `A->C` remains an active depth-zero tie. A subsequent
neutral extension `T->H` causes capitulation; `C->H` or `C->C2` succeeds; `T->T2`
refreshes the episode to anchor T, trigger T2, depth zero.

## Fork choice, propagation and target strategy

Filter by policy eligibility and the reduced visibility window, then keep the
highest eligible blocks. Apply ownership only to those competing tips:

* An explicit actor owning an eligible tip extends it deterministically. If it
  owns several, it uses its most recently published eligible tip.
* The oceanic residual never gets ownership privilege, including after its own
  label appears as a first publisher or competing tip owner.
* With no target-owned competing tip, neutral support is uniform among n tips.
* With exactly one target-owned competing tip and n>1, that tip gets gamma;
  each other tip gets `(1-gamma)/(n-1)`. Binary ties reduce to gamma/1-gamma.
* A target block in ancestry alone gives no influence advantage. A single
  eligible tip is chosen with probability one and no tie RNG draw.

Multiple simultaneous target-owned highest competing tips are unsupported.
Publication checks the global competing frontier before mutating the public
ledger; actor-specific fork choice also checks its eligible frontier. A run
encountering such a state reports `UNSUPPORTED_STATE`, retains diagnostics, and
cannot be included as a completed statistical repetition.

Natural lambda forks use an explicit reduced one-discovery visibility window,
not a network propagation simulator. An ordinary single leading publication can
open a window with probability lambda. On the next discovery another explicit
actor, or any oceanic residual discovery, temporarily excludes that block from
its mining view. Its eligible highest parent may then generate a natural sibling.
The original explicit publisher continues its own branch. A window is consumed
once; neither opening a tie nor resolving a previous window opens another window
in the same step. Public announcements still reach the policy immediately.

These windows continue during retaliation when their usual conditions hold.
An active member's policy-prescribed work is tagged `counter_fork`; a neutral
delayed sibling is tagged `natural_fork`. Natural-pair counters count the latter,
including residual/residual discoveries as distinct oceanic miners. Lambda zero
does not eliminate intentional counter-forks. Windows are not opened while
target-private state or an existing global leading tie is being processed.

The target uses one independent selfish strategy in the new tree model:

* With private work, its discoveries extend its own hidden chain without a lead
  cap. With none, it starts a hidden chain from its chosen public parent, except
  that a discovery resolving an existing public leading tie is published.
* Following a new competitive public advancement, compare the private tip height
  to the competing public height. A negative lead abandons the hidden suffix;
  a lead of zero or one releases the whole private suffix atomically; a larger
  lead releases the prefix through the rival's height and retains the rest.
* Published prefixes can participate in public retaliation while a hidden suffix
  remains. Release itself creates no discoveries. Abandoned private blocks remain
  in the terminal ledger but the strategy does not resume mining them.

This is the explicitly versioned persistent extension of the target strategy.
It is not asserted to reproduce v4 traces: v4 irreversibly settles races and
does not permit this coexistence of private leads and persistent public forks.
The gamma and explicit-versus-oceanic choice rules above are retained. Only the
existing v4 engine is the historical compatibility path. Broader statistical
calibration of the new target extension remains work before a production study.

## Observation and boundary diagnostics

The separate runner defaults to **30,000 reference-chain blocks and 20 independent
repetitions**. Tiny explicit overrides exist for tests; no production configuration
has been changed. The run stops after the first complete discovery step (including
its endogenous publication responses) that reaches the height target. An atomic
release may overshoot the target. There are no extra discoveries to settle a tie,
no forced release, no forced capitulation, and no confirmation-depth parameter.
Payoffs divide individual current canonical rewards by the observed reference
height, including any atomic overshoot.

The terminal record includes:

* Full canonical block records and ordered canonical IDs.
* Every public leaf and every unpublished leaf, including stale and abandoned
  branches; all noncanonical block records, deduplicated by block ID.
* Each alternative's complete divergent path, common canonical ancestor, height,
  visibility, number of canonical blocks exposed and their individual owners'
  reward counts.
* The active target-private chain, abandoned private IDs, pending visibility
  block and active punishment snapshot. Publication batches and completed episode
  history remain in the raw result as well.

`complete-frontier-conservative-v1` marks the endpoint potentially material when
any alternative, active punishment or visibility window remains. It reports the
maximum exposed canonical suffix and worst-case per-actor payoff bounds `[0,1]`.
These are deliberately conservative **bounds, not confidence intervals** and not
a claim that every stale branch will return. Retained historical stale forks
can make the flag very common and the bound uninformative. A clear flag only
describes the recorded endpoint; it is not a theorem about future discoveries.
No old private-lead-only omission bound is used for persistent public forks.

`max_events` is a resource guard, not a scientific settlement rule. Exhaustion
reports `INCOMPLETE_RESOURCE_LIMIT`; unsupported and incomplete conditions raise
`IncompleteStudyError` in a study. The runner writes a failure artifact and no
complete checkpoint for that task. No incomplete repetition is silently dropped,
replaced, counted as success or given an ordinary payoff classification.

## Conditional statistics and CRN

Every population/repetition evaluates H, S0, HF(C), SC(C), and each
SC(C minus j), deduplicating identical conditions. All retain the same explicit
actor population, including neutral omitted members. Each condition constructs
its own tree, private state and punishment policy. It never copies retaliation
state from a different condition.

The seed is `population.seed + repetition`, with independently seeded discovery,
tie and natural-window streams under the new engine namespace. Matching seeds
pair conditional outcomes within a repetition; repetitions use distinct seeds.
Stream consumption can diverge across conditions, as with the existing CRN
method. No variance reduction is assumed: existing paired-versus-independent
variance diagnostics remain available.

The adapter fills every required old reducer cache key with validated **new**
conditional observations. A missing key raises; the historical mining fallback
cannot run. No historical simulation output is loaded into this bridge. The
unchanged reducer computes D=H-SC, B=SC-S0 and Q=SC-SC_without_j, sample standard
deviations, standard errors, paired 95% intervals, supported/refuted/inconclusive
statuses, detector mixtures and false-positive costs. At 20 repetitions it uses
the existing t(19) critical value 2.093. Existing strict/weak distinctions and
the refined weak/strict joint-feasibility classifications are retained.

The legacy `winning` definition remains effectiveness plus deviation-proofness;
the separately named joint-feasibility fields also require baseline credibility.
Continuous TPR thresholds retain the existing paired bootstrap and its valid/
invalid draw counts. All statistical classifications describe finite-horizon
canonical payoffs; sampling CIs do not incorporate unresolved-fork uncertainty.
The boundary fields are reported separately and do not silently change the
statistical method. There is no staged follow-up repetition design.

## Identity, checkpoints and local use

Model version, `punishment_rule` and `counter_fork_k` are included in mining
keys, population configuration IDs, task IDs, manifests, output metadata, every
CSV family and analysis grouping. Cache keys additionally distinguish seed,
population, horizon, target strategy, flag and active coalition. Task IDs include
requested coalition sets. Analysis groups also distinguish environment, horizon,
repetition count and composition structure. Thresholds are minima among supplied
grid points; missing support is not proof that no feasible configuration exists.

The new schema is **`persistent-conditional-checkpoint-v1`**. It stores exact
specification identity, repetition count, seed schedule and all raw conditional
results with a SHA-256 content digest. Loading checks schema, manifest, coverage,
per-condition model/rule/population/seed, publication ancestry/order, complete
ledger, reference height, canonical membership, actor accounting and payoffs.
The digest detects changes, not malicious producers; it is not an attestation.

Historical v3/v4 checkpoints are ineligible, including lambda-zero checkpoints.
Changing repetitions or k requires a new manifest. No truncation, partial reuse
or automatic historical import is implemented. Invalid existing checkpoints
raise rather than triggering fresh mining. Analysis-only requires all validated
native checkpoints and cannot fall back to simulation. The runner refuses a
nonempty directory without its own manifest or with a different design.

The separate entry point is `python -m punishment_sim.persistent_sweep`. It takes
an explicitly supplied JSON configuration and `--output`; `--dry-run` calculates
scope only and `--analyze-only` reuses native checkpoints. Its default model must
be specified explicitly with `expected_model_version="persistent-counter-fork-v1"`.
There is no default k or automatic k grid. Supported design fields are checked
in `prepare`; population grids use the existing pure task generator. Stored
historical environment-admission files are rejected. Explicit analytical
Eyal–Sirer domain selection is available as a grid filter, not a claim about the
new engine's measured profitability.

Outputs comprise coalition results, member credibility, detector evaluations,
repetition metrics (including terminal frontiers), continuous TPR thresholds,
grouped minimum thresholds, full JSON results, native checkpoints and a manifest.
Retaining full ledgers makes this foundation storage-intensive; production
performance, compact encodings, distributed scheduling and cross-model checkpoint
conversion are not implemented or benchmarked.

## Validation and next policy

Run the two new test files with pytest, then the complete existing local suite.
Tests cover publication-only triggering, stale/duplicate rejection, misses and
false positives, exact k deadlines, ties/overtakes, repeated/atomic refresh,
eligibility/ownership/gamma, natural forks, independent leaveouts, reversible
individual rewards, accounting conservation, unresolved height-30,000 state,
atomic horizon overshoot, resource/unsupported failures, deterministic streams,
20-repetition paired statistics and fail-closed cache/checkpoint/analysis paths.
The 30,000-height fixture is a scripted state test, not a stochastic production
experiment. Runner fixtures use height 12 and two repetitions.

Ostracism should next implement another policy against the existing tree and
reorganization interfaces: arm on detection, reject the first qualifying offending
target root and descendants, grandfather preceding history, retain rejected roots
without timeout, and remain armed after a conflict is orphaned. Add deterministic
eligibility/reactivation and terminal-frontier tests before any production design.
Use an explicit new policy/model identity. Ostracism, independent selfish coalition
miners and combined policies are intentionally absent from this implementation.
