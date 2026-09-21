# Common persistent network v2

Current production planning is documented in [the 0.51 cutoff and fixed 5+5 workflow](persistent_v2_51pct_phased_production.md). Earlier scope/runtime figures below remain historical evidence.

The current intended study uses **10 repetitions everywhere** and
[compact repetition checkpoints](persistent_v2_compact_production.md). That
follow-up supersedes the earlier full-ledger production storage/layout and
twenty-repetition planning figures; historical measurements remain dated evidence.

The [production-readiness follow-up](persistent_v2_production_readiness.md)
documents the v2-only owner correction, persistent petty, exact indexes,
production recording layout and fixed local 30,000-block benchmarks. It updates
the initial performance limitations and test counts below; network/RNG/stopping
conventions remain unchanged.

The v2 persistent models implement the same network and target strategy, with
punishment attached only when the conditional flag and active coalition are both
nonempty. H and S0 have no punishment instance. Their complete native results,
including traces and RNG states, are identical across rule selections. This
corrects the two independent inconsistencies in the
[historical v1 audit](persistent_baseline_audit.md).

| Component | Semantic identity |
| --- | --- |
| Common network | `persistent-network-v2` |
| Shared inactive condition | `persistent-common-baseline-v2` |
| Petty tie-breaking | `persistent-petty-v2` |
| Counter-fork | `persistent-counter-fork-v2` |
| Ignore | `persistent-ignore-v2` |
| Selfish counter-mining | `persistent-selfish-counter-v2` |
| Propagation | `public-announcement-frontier-one-discovery-v2` |
| Reaction ordering | `public-snapshot-rounds-population-order-v1` |
| RNG | `sha256-python-random-common-streams-v2` |
| Observation endpoint | `completed-discovery-reference-height-no-finalization-v2` |

## Exact public-event and propagation rule

Each step contains exactly one real discovery. A withheld discovery creates no
public announcement or propagation opportunity. A public discovery is published,
then all immediate strategy reactions finish before another miner can discover a
block. Each private-chain release is one atomic, ancestor-to-descendant batch.
Publication counters retain the order within a batch; those counters do not
represent mining events or additional propagation trials.

Call the discovery and its complete publication/reaction cascade an announcement
episode. The episode is eligible for one lambda trial exactly when:

1. There was no incoming propagation window.
2. The public tree had at most one globally leading tip before the discovery.
3. The newly discovered block is public and its height exceeds the public height
   immediately before that discovery.

The trial occurs **after all immediate releases and reaction rounds**. It consumes
one natural-stream variate even at lambda zero. A draw strictly below lambda
creates a window containing the episode's ordered publication IDs and the subset
that are final public leaves after the cascade (`delayed_tips`). It does not
inspect any private lead or suffix length. No extra trial is generated per batch,
per released block, or by a direct low-level fixture call to `publish()`.

Only those newly published **leaf tips** are delayed for the next ordinary public
miner's parent choice. Interior published prefixes remain visible. This is an
explicit reduced propagation abstraction: one event can delay several competing
new tips with one shared Bernoulli decision. It does not simulate independent
packet delivery or per-miner latency. A public discovery behind an existing
global maximum, and a discovery resolving an already visible leading tie, do not
open a fresh window under this convention.

An explicit miner knows its own published tips; the oceanic residual represents
distinct small miners and gets no ownership persistence. Target/member selfish
actors extend their own hidden suffix when they have one. Otherwise they choose
from the full policy-eligible public view and use the existing convention of
publicly resolving a leading tie or starting a private suffix when there is no
leading tie. Strategies observe atomic public announcements immediately. These
information conventions apply equally under every rule; lambda models delayed
ordinary public mining, not a general network transport protocol.

The incoming window expires after the next real discovery, including a private
discovery or an owner's extension. Any release at that next discovery remains
atomic; it neither extends the window nor draws again. If the delayed view lowers
an ordinary actor's best eligible parent height, its public discovery is recorded
as `natural_fork`. It can create a sibling of a delayed tip. Once the window is
consumed, subsequent steps see the resulting public branches and use the common
fork manager. An active counter-fork/ignore action retains its intentional policy
label even if its parent view was delayed. The diagnostic `delayed_source` selects
the earliest-published hidden tip among the full-view highest eligible tips; the
pair count is a discovery attribution, not a count of all races or releases.

For example, after two private target discoveries and one residual discovery,
publication order is `[H1, T1, T2]`. The release `[T1, T2]` is atomic. A successful
trial delays final tips `{H1, T2}`; T1 remains visible. The next neutral miner can
mine a sibling of T2 on T1. A counter-fork triggered by T2 also retains its exact
parent anchor T1. With three private target discoveries, the same residual
publication releases only T1, retains `[T2, T3]`, and can delay `{H1, T1}`. Both
episodes get one trial by the same public rule. Exhausting or retaining a private
suffix never gates the trial.

## Strategy and accounting separation

`persistent_v2.PersistentSimulation.step` is the sole discovery path for all
conditions. Its initializer does not construct a disabled v1 policy. The generic
`SelfishActors` controller manages the target's private state and, only for
flagged selfish counter-mining, an independent state for each active member.
Release decisions use the unchanged `selfish_strategy.release_plan`, each
actor's own private chain, and a common public snapshot. Decisions in a round are
committed in population order; new publications feed another snapshot round.
Each reacting round removes private work through release or abandonment.

Counter-fork retains defended-branch-depth k, refresh on target publication,
success and capitulation. Only final leaf tips can be delayed, so a trigger's
parent anchor remains eligible; no fallback silently changes that strategic
anchor. Ignore retains rejected-root ancestry and never capitulates. Independent
selfish members have no pooled private chain, coalition gamma or reward sharing.
Leaving the coalition changes strategy membership, not population or hash power.

All conditions use the same persistent ancestry tree, target-only gamma rule,
explicit-owner tie preference, oceanic residual semantics, sticky reference
choice at equal height, full reorganization and owner-level reward accounting.
Historical block-tree/accounting helpers and strategy primitives are reused
without editing their v1 source. The v1 initializer and v1 discovery dispatch are
not called by v2.

The endpoint remains the first completed discovery/reaction episode whose
reference height reaches or exceeds the configured target (default 30,000).
Atomic releases may overshoot that height. There are no settlement discoveries,
forced private releases or finalization claims. Full unresolved branch/private
state and pending propagation survive in the endpoint record. If unresolved,
the reported conservative future-payoff bounds are [0,1], distinct from sampling
confidence intervals. Resource-limited and unsupported results cannot enter
completed-condition stores or statistical analysis.

## RNG, pairing and the seed-84 regression

The three independent common streams are named `discoveries`, `natural`, and
`ties`. Their Python Random seeds are the first eight SHA-256 bytes of:

```text
persistent-network-v2:sha256-python-random-common-streams-v2:<base_seed + repetition>:<stream_name>
```

No punishment rule, k, flag, coalition, target strategy, gamma or lambda is in
that RNG namespace. Population thresholds map common discovery variates to
miners. Environment parameters determine how common tie/propagation variates
are used. This deliberately permits matched randomness across conditions and
environments without pretending those environments have identical behavior.
Snapshots record draw count, last draw and full RNG-state hash.

H, S0, HF, SC and leave-one-out SC begin with corresponding identical streams.
Every native step consumes exactly one discovery draw, so equal-length discovery
prefixes match. Tie draws occur only for actual non-owned multi-tip choices;
natural draws occur only at eligible public episodes. Endogenous divergence can
therefore change which discovery consumes the next tie/natural variate. This is
shared sequential-stream CRN, not a claim of permanent event-index coupling for
those two streams. Current policies need no RNG of their own. A future stochastic
policy must add a separately versioned policy stream without consuming common
streams for its internal decisions.

The historical audit's first native mismatch was RNG initialization (event zero),
leading to different discoveries from event one in its seed-701 comparison.
Even with streams manually aligned, the old seed-84 example diverged at event
four because one v1 dispatch opened a propagation window while the others
suppressed the trial due to private work. Parent choice and rewards then diverged
at event five. Both causes are removed in v2: common seeds and one public rule.

The permanent seed-84 fixture supplies owners
`target, target, target, honest_residual, c1`. Forced owners are explicitly marked
as scripted and are ineligible for native checkpoints. With **native v2 tie and
natural streams**, event four publishes `[4,1]`, retains private `[2,3]`, and all
three rules consume natural draw `0.48230038689431753`. Thus no window opens at
lambda 0/0.005/0.02. Event five consumes tie draw `0.33589957533534676`, extends
T1, releases `[2,3]`, and ends on `[1,2,3]` under every rule. New versions do not
reinterpret the old numeric stream at the same integer seed.

A separate, clearly scripted diagnostic injects the historical natural variate
`0.00027760641597729396`. At lambda 0.005 and 0.02 all three v2 paths now open the
same event-four window on `[4,1]`. At event five c1 mines from genesis, takes no
tie draw, and leaves target private `[2,3]`; the reference remains `[4]`. Complete
results agree here too. Lambda-one lead tests independently exercise successful
delay without overriding any natural variate.

## Shared H/S0 identity and provenance

`persistent_v2_checkpoint.ConditionStore` has separate namespaces:

```text
baselines/<condition_digest>.json    persistent-common-baseline-checkpoint-v2
conditions/<condition_digest>.json  persistent-policy-conditional-checkpoint-v2
```

The new identity includes network, propagation, reaction-order, RNG and stopping
versions; full ordered population/hash powers; target gamma and lambda; base
seed, repetition and actual seed; target strategy and accepted-height target.
An inactive identity uses the common baseline model, `rule=null`, `flagged=false`
and an empty active coalition. Active identities include the selected v2 rule
and k. The total requested repetition count is not part of a per-repetition
condition identity. Detector TPR/FPR, prior and bootstrap count are downstream
analysis inputs. A resource cap does not alter a successfully completed path;
an exhausted cap never supplies a completed reusable result.

Each file contains schema, identity, raw result, and a SHA-256 of that envelope.
Loading validates all of them and reconstructs native discovery draws, parent
choices, lambda trials/windows, publication batches, every required strategy
reaction, private state, policy history, complete terminal tree, rewards and RNG
states from the recorded ledger. Missing release reactions are checked even if
their history frames were also omitted. Validation never calls simulation
`step`, `discover`, `publish` or `run`. It does read and evaluate the whole recorded
trajectory; analysis-only is not computationally free.

Historical schemas/results, altered identities, scripted owners, incomplete
results and corrupt cached data fail closed. There is no v1 importer, relabeling,
truncation, silent cache-miss substitution or historical mining fallback. A
different result cannot overwrite an existing validated condition. Run outputs
carry baseline references with condition ID and raw-result content hash; the
file envelope's checksum additionally covers its schema and identity. Consumer
rule metadata belongs on study rows, not on the shared baseline result.

`persistent_v2_study.study` accepts a shared `checkpoint_dir` or in-memory cache.
`analyze_only=True` requires all conditions and forbids mining missing data.
`persistent_v2_sweep` is a separate explicit runner; a design must name both the
matching v2 network and rule version. It defaults to 10 repetitions and 30,000
accepted-height target. It adds no production grid. Separate rule outputs can
point to one shared condition directory. Scope describes represented work before
validated reuse; its dry-run mode does not simulate. The historical runner and
petty v4 configuration are unchanged.

## Statistical comparison and verification

The existing paired reducer, sample SD, standard error, Student-t 95% intervals,
supported/refuted/inconclusive classifications, weak/strict feasibility,
detector mixtures and TPR bootstrap are preserved. With shared stores, D uses
the exact same per-repetition H result for every rule; B uses the exact same S0
result. Q compares full and leave-one-out active sets under one v2 network and
unchanged population. Bootstrap seeds retain the existing configuration-derived
analysis convention and do not enter mining RNG.

The earlier compatibility suite included a 20-repetition test study at 12-block
horizons (not the current ten-repetition research design). For two members it
executed 120 condition runs for the first rule and 80 for each subsequent rule,
reusing the same 40 H/S0 results. It verifies baseline result hashes and values,
paired D/B/Q statistics, classifications, detector mixtures, disk reuse and
analysis-only reconstruction with mining methods disabled.

Native exact-equality tests compare entire H and S0 results at lambda
0/0.005/0.02/1 and seed/repetition combinations (84,0), (701,0), (12,2), including
initial RNG state, every trace field and terminal state. They use no normalization
or forced RNG. Additional tests cover inactive k and coalition labels, private
leads 1/2/3/12 under each rule, pending windows, suffix exhaustion and retention,
atomic releases, policy invariants, independent members, conservative endpoints
and checkpoint corruption. Thirty-two new full-trace digest fixtures preserve
v2 behavior separately from the existing v1 fixtures.

All eight v1 runtime modules match the source hashes captured in the pre-change
audit. Its nine strict expected failures remain explicitly v1-only; corresponding
v2 invariants pass. The historical v1 trace/checkpoint/export fixtures remain
unchanged. No historical petty v4 file or running sweep was touched.

Validation on 2026-09-16: the three v2 test modules passed **135 tests**; the full
`.venv/bin/python -m pytest -q` suite passed **818 tests with 9 historical-v1
expected failures** in 54.59 seconds. `git diff --check` passed, as did explicit
whitespace checks on all 11 added/updated files, including untracked additions.

No unresolved cross-rule baseline choice remains in this implementation. The
one-discovery leaf-delay and immediate strategic observation conventions above
are explicit modeling assumptions, not empirically calibrated transport claims.
Multiple simultaneous target-owned competing tips still fail explicitly rather
than silently inventing a gamma allocation. Full ledgers and ancestry scans can
have substantial memory and superlinear runtime costs. No production benchmark
or scalability claim accompanies this correction.

Only local tests and tiny fixtures were run: no production simulation, SSH,
`/xtra` access or remote job.
