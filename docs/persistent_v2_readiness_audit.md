# Persistent v2 readiness audit — 2026-09-21

This is the **pre-change audit**. The subsequent
[implementation and local benchmarks](persistent_v2_production_readiness.md)
close the owner gap, add persistent petty and replace full-history eligibility
scans. Its historical gap reproduction uses a frozen reference engine; the
findings and original evidence below are preserved as the comparison baseline.
The current intended design is the subsequent
[ten-repetition compact workflow](persistent_v2_compact_production.md); the
twenty-repetition scope and recommendations below are historical.

**Do not launch the production grid yet.** The normal counter-fork examples work
for k=1,2,3, but the publication callback lacks an explicit active-owner exclusion.
Petty-v4 versus persistent-v2 is **classification C: different network models**.
All 100 bounded performance/correctness probes completed and reproduced exactly.
The main measured cost is repeated full-public-set eligibility scanning, shared
by all three persistent policies. No model, production configuration or running
experiment was changed.

Reproducible evidence:

- [Bounded audit program](../analysis/audit_persistent_v2_readiness.py).
- [Machine-readable results and source hashes](persistent_v2_readiness_evidence.json).
- [Focused regression/audit tests](../tests/test_persistent_v2_readiness_audit.py).

The evidence records unchanged SHA-256 hashes for all 32 simulator Python files
and the existing refined petty-v4 configuration. No SSH, `/xtra` access, remote
job, production sweep or 30,000-block benchmark occurred. Diagnostic stream
alignment and forced-owner sequences below are explicitly distinguished from
native simulation/checkpoint provenance.

## 1. Exact counter-fork behavior

V2 reuses `CounterForkPolicy.on_publication` in `punishment_sim/persistent.py`.
The current implementation:

1. On a newly published qualifying target block T, challenges T from parent(T).
   Active members choose the highest visible eligible branch descending from
   that anchor and excluding descendants of T; an existing counter-branch can
   therefore be extended instead of restarting at the anchor every discovery.
2. Defines a qualifying target as a newly published target ancestor of a globally
   highest public tip, evaluated on the complete post-batch public tree.
3. Processes every qualifying target publication in order **before** timeout
   accounting. Each refresh resets depth and the defended high-water height to
   the new target. The last qualifying target in an atomic release is current.
4. Counts a newly published non-target descendant of the current trigger only
   when it exceeds the defended high-water height. Depth increases by the height
   difference, and the high-water mark advances. This is not a count of all
   publications or discovery events.
5. Declares success when the reference excludes T and is strictly higher than
   every public T-descendant leaf. Success precedes timeout within a batch.
   Otherwise depth >= k causes capitulation and ordinary fork choice resumes.

The clarified normal examples all pass:

| Event | Current behavior |
| --- | --- |
| A→T1, then A→C1 | Active at depth zero, including k=1 |
| Nonparticipating c2 or residual extends T1 | Defended depth increases by one |
| k successive ordinary defending levels | Capitulation at exactly k |
| T1→H1→T2 at k=2 | Refresh on T2, anchor H1, depth zero; no intervening capitulation |
| T1→T2 at k=1 | Refresh on T2, anchor T1, depth zero |
| Coalition or neutral assistance on the counter-branch | No timeout increment; a strict overtake succeeds |
| Unrelated branch activity | No timeout increment |
| Two defending siblings at the same height | One depth level in total, not two |
| Natural sibling at an already reached defending height | No extra depth increment |

Height is a valid proxy on the normally reachable path: coalition parent
eligibility prevents members from extending the challenged branch; an ordinary
public discovery advances at most one level; qualifying target extensions reset
before timeout. Leave-one-out miners remain in the population and count as
ordinary defenders. A natural discovery that actually creates a new maximum
defending level can legitimately count; the natural label alone does not count.
The 100-probe observer also checks that a native active coalition discovery never
descends from its pre-discovery challenged target.

### Exact-conformance gap, left unchanged

The callback tests `owner_id != "target"`, **not** membership outside the active
coalition. A direct fixture can publish an active c1 block on the defended
branch. At prior depth k−1, this causes `CAPITULATED` at depth k, while the clarified
non-coalition definition would retain depth k−1. This is reproduced for all three
k values. Such a publication is excluded by current native counter-fork parent
choice; no normal-run violation was observed. Nevertheless, the callback itself
does not enforce the stated actor distinction.

A correction should either explicitly reject that out-of-policy publication
as unreachable or implement owner-aware defending depth if such publications
are to be permitted. Merely adding an owner filter while leaving an old
high-water height can count the skipped coalition height later when an honest
descendant arrives. That detail needs a regression test with a later honest
extension. No correction was made during this audit, and historical v1 must not
be silently changed by a future correction to its currently shared policy class.

There is one additional convention to make explicit: current refresh is not
restricted to descendants of the previous trigger. At k=2 or 3, the native forced
schedule `target, residual, c1, c1, target`, with neutral tie variate .75, lets the
last target extend the counter-branch. The old trigger is excluded, and the code
records `REFRESHED` and challenges the new target there. This implements the
general principle of challenging each newly competitive target block, but its
episode outcome is not “old target succeeded, then new challenge.” The supplied
defended-branch refresh example does not specify that off-branch bookkeeping;
it should be documented explicitly before freezing production semantics.

**k readiness:** all three values are operational and materially distinct: k=1
allows the initial contest but no completed ordinary defending extension; k=2
survives one; k=3 survives two. Each resets on target refresh. The intended grid is
appropriate, but exact-contract production sign-off should wait for the owner
guard decision/correction and explicit off-branch episode convention. These are
not reasons to change the numeric k grid.

## 2. Petty-v4 versus persistent-v2

Comparison population: target .20, c1=.10, c2=.10, residual=.60, gamma=.5,
seed=701, repetition zero, horizon 200, unflagged H and S0, separately at lambda
0, .005 and .02. Twelve paired cases comprise six native comparisons and six
diagnostic comparisons with every RNG initialized to the same v2 stream.

Instrumentation records discovery owner/order, parent/height/withholding,
publication order, release batches, natural discoveries/pairs, pending delayed
tips, target private chain, historical public frontier, canonical/reference
chain, rewards and all RNG counts/state hashes. Endpoint snapshots and discovery
counts are retained. V4 has no equivalent full persistent terminal object;
its accepted chain/private/pending/race state is compared rather than pretending
the different schema names are behavioral differences. A “none” first difference
means equality over the common observed prefix; endpoint event counts are also
reported separately.

### First differences

All six **native** pairs differ in RNG initialization at event zero:
`explicit:<seed>:<stream>` versus the versioned common-v2 namespace. In this
seed-701 fixture, both first discoverers are residual; the first different owner
is event **2**, petty-v4 c1 versus v2 c2, for both H and S0 at every tested lambda.
This alone would not establish different scientific laws, so aligned controls
and deterministic semantic counterexamples were also run.

| Aligned case | First canonical/reward difference | First different parent | Endpoint discoveries, v4 / v2 |
| --- | ---: | ---: | ---: |
| H, lambda 0 | None | None | 200 / 200 |
| H, lambda .005 | 101 | 171 | 201 / 202 |
| H, lambda .02 | 101 | 159 | 204 / 205 |
| S0, lambda 0 | 9 | 19 | 241 / 241 |
| S0, lambda .005 | 9 | 19 | 241 / 241 |
| S0, lambda .02 | 9 | 19 | 241 / 244 |

At aligned H event 101, draw .001563147771243667 opens the same pending delay in
both positive-lambda cases. V4 defers crediting that pending block; v2 immediately
puts it on its provisional reference chain. That earliest difference is an
accounting/reference convention, not yet a changed parent. At lambda .005,
event 171 is residual following a residual pending publisher: v4 extends the
pending block, while v2 creates a sibling. At lambda .02, event 159 first differs
because v4's target-first probability interval and v2's sorted-tip intervals map
the same tie variate to different branches; that difference alone has the same
branch probabilities. The **material propagation-law difference** appears at
event 177, again residual following a residual pending publisher.

The two-event diagnostic `residual, residual`, using natural variate .001 at
lambda .005 or .02, isolates that law difference immediately:

- Event 1: both publish block 1 and delay it, but v4 has no accepted tip yet while
  v2's provisional reference is block 1.
- Event 2: v4's pending branch compares the aggregate label with the publisher
  label and extends block 1. V2 gives oceanic residual no publisher-ownership
  persistence, hides block 1 and mines a sibling from genesis.

The oceanic ownership correction in v4's **race choice** does not extend to its
separate `actor != pending_publisher` test before a race is created. This audit
does not alter that historical behavior.

In aligned S0, event 8 is a withheld target block and event 9 publishes a rival
and releases it. V4 opens a two-way race without crediting either contender;
v2 provisionally adopts the earlier rival and consumes a common public-episode
lambda trial. V4 makes no such trial while handling this private release.
At events 15–18 the target has three private blocks and exposes one prefix;
event 19 chooses different parents because v4 has already accepted that prefix
and discarded the rival, while v2 retains the public competition and takes a
tie draw.

The five-event diagnostic `T,T,T,residual,c1`, seed 84, common natural variate
.001 and common tie variate .75, makes the distinction shorter. At event **4**,
both expose residual block 4 followed by target block 1 and keep private `[2,3]`.
V4 credits target block 1 and orphans block 4 immediately. V2 keeps both public,
retains block 4 as reference, and makes one lambda trial even at lambda zero.
At event **5**, parent choice differs even at lambda zero. At positive lambda,
v2 additionally opens/consumes the public delay and creates a natural sibling;
v4 suppresses that propagation opportunity during private-release handling.
These forced-owner/variate cases are diagnostic fixtures, never native caches.

### Classification C and what the current petty results mean

V4 estimates petty tie-breaking in its reduced lead/race/pending-block model:
one local two-way public race at a time, no simultaneous public race and retained
private suffix, immediate prefix credit/rival orphaning for long private leads,
single pending-block propagation, and a stopping rule based on irreversible
accepted accounting with race/pending cleanup. Unreleased private work is left
uncredited. V2 retains a public tree, provisional reference rewards and reversible
reorganizations, shares an episode-level delayed-tip law with private strategies,
and stops after the complete episode reaching reference height without settlement.

The running petty experiment is **not declared invalid**. It remains an experiment
under its own versioned assumptions. It is not directly usable as the petty arm
of a strict “same network, different policy” four-rule comparison. Nor does this
audit establish general distributional equivalence after dropping CRN. A future
petty policy on persistent-network-v2 is needed for that strict comparison; none
was implemented here. Descriptive comparisons of separately labeled models are
possible, with the network/endpoint differences made explicit.

## 3. Bounded validation and performance results

Environment: Python 3.13.3, Darwin arm64, one local process. Each composition has
total coalition power .20: c1=.20, or c1=c2=.10; target=.20, residual=.60, gamma=.5.
Lambda is 0 or .02. The five variants are counter k=1/2/3, ignore and selfish.

There are **80 SC probes** (five variants × two compositions × two lambdas ×
200/500 horizons × two repetitions, actual seeds 701/702), plus **20 HF smoke
probes** at horizon 200 and seed 701. Each has an exact uninstrumented rerun and
strict native checkpoint validation. Five additional horizon-500 cProfile runs
identify hotspots; their instrumented timings are not in the runtime medians.
The initial pilot and measurement pass were followed by the recorded pass after
adding the native coalition-parent assertion. Timing variability is expected;
these short runs are implementation diagnostics, not scientific findings.

Engine wall time includes construction, mining, lightweight invariant/peak
counters and endpoint reporting. Serialization includes envelope hashing and
compact JSON encoding; validation is timed separately. No disk throughput,
worker scaling or large-grid throughput is inferred from these measurements.

| SC variant | Median 200-block engine ms | Median 500-block engine ms | 500 / 200 runtime | Median 500-block validation ms |
| --- | ---: | ---: | ---: | ---: |
| Counter k=1 | 9.96 | 47.00 | 4.72× | 65.29 |
| Counter k=2 | 10.44 | 49.60 | 4.75× | 70.92 |
| Counter k=3 | 11.55 | 49.96 | 4.33× | 72.43 |
| Ignore | 12.93 | 65.35 | 5.06× | 89.52 |
| Selfish | 12.11 | 59.31 | 4.90× | 81.32 |

The following ranges cover the eight 500-block SC observations per variant:

| Variant | Discoveries/reference block | Retained blocks, maximum per run | Public leaves, maximum per run | Simultaneously nonempty private states | Maximum private lead | Reorganizations/run | Maximum removed reorg depth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Counter k=1 | 1.216–1.228 | 608–614 | 99–105 | 1 | 5–6 | 56–68 | 2–4 |
| Counter k=2 | 1.234–1.262 | 617–631 | 104–115 | 1 | 5–6 | 58–65 | 2–5 |
| Counter k=3 | 1.258–1.272 | 629–636 | 106–116 | 1 | 5–6 | 62–66 | 4–5 |
| Ignore | 1.534–1.600 | 767–800 | 111–118 | 1 | 5–6 | 82–87 | 3–5 |
| Selfish | 1.402–1.446 | 701–723 | 185–206 | 2–3 | 5–6 | 107–116 | 2–4 |

Public leaves include archived stale branches, not just currently tied leading
branches. Retained block-store size equals the number of actual discoveries in
every probe; there is no unexplained duplication or loss. Private lead is tip
height minus current public height, maximized over actors and discoveries.
Maximum private suffix length also ranged 5–6 here; there is no imposed cap.

| Variant | Compact checkpoint bytes at 500 | Median endpoint-report ms | Median hash/serialization ms |
| --- | --- | ---: | ---: |
| Counter k=1 | 429,028–436,426 | 1.29 | 5.03 |
| Counter k=2 | 437,090–448,640 | 1.37 | 5.36 |
| Counter k=3 | 444,788–451,650 | 1.37 | 5.38 |
| Ignore | 544,579–567,731 | 1.73 | 6.37 |
| Selfish | 508,840–531,275 | 1.63 | 5.91 |

Sizes include the native conditional envelope and full required ledger/event
provenance, trace mode off. Actual store encoding adds a newline. The evidence
also reports indented JSON sizes, but compact encoding matches the native store.
Endpoint serialization does **not** dominate the measured engine runtime.
Strict validation costs more than a mining run in these probes.

For selfish SC at horizon 500, moving from one to two active members at fixed
total coalition power increased median engine time from **57.38 to 60.79 ms**,
about **1.06×**. Allocated private-state slots, including the target, increase
from two to three; all were simultaneously nonempty at some point. Maximum
retained public leaves increase from 185–191 to 194–206. This is modest at the
tested point, not evidence of benign scaling for six members or every grid cell.
HF horizon-200 engine medians are 8.12/8.43/9.05/9.00/9.22 ms respectively for
counter k=1/2/3, ignore and selfish; their individual diagnostics are in the JSON.

### Correctness and boundary observations

- All 100 probes completed at the first complete episode meeting the horizon;
  94 hit it exactly and six overshot by one block through atomic release.
- No post-horizon discovery or forced publication/private settlement occurred.
- Discovery and reward accounting conserved at every observation; final actor
  discovered = accepted + public-noncanonical + unpublished held throughout.
- No resource limit, censoring event, unsupported-state exception or multiple
  target-tip invariant violation occurred. Every same-seed rerun was exact.
- All 100 endpoints were flagged potentially material/unresolved, with
  **payoff-bound width 1.0** ([0,1]) for every actor. Four retained active private
  state at the endpoint; the broader unresolved flag also includes public stale
  alternatives, policy state and delay. It is not a failure to terminate.

The [0,1] future-continuation bounds are conservative and uninformative here;
they are not sampling confidence intervals. These probes do not establish that
30,000 blocks removes endpoint effects, or that a reported finite-horizon payoff
has converged to a stationary long-run payoff.

## 4. Scaling concerns and behavior-preserving next work

Horizon increases by 2.5× but observed median engine runtime increases 4.33–5.06×.
This is clear superlinear growth at small sizes, consistent with the quadratic
scan structure; two horizon points alone do not estimate a reliable asymptotic
exponent. Profiles put **69–76% of run time in `persistent_v2.eligible_tips`**,
which materializes candidates and scans for height twice. A horizon-500 profile
makes roughly 699,000–909,000 `height()` calls from only 612–769 discoveries.
`visible_public` also copies the public set. Ordinary actors scan old public
blocks despite the engine already maintaining frontiers. Ignore has cached
rejected ancestry and eligible-frontier information, but the v2 eligibility path
still scans the visible public set. Ancestry traversals exist elsewhere, but the
dominant measured issue is these full-set scans, not private-state coordination.

Clear candidates for future optimization, preserving exact trace/RNG results:

1. Maintain indexed eligible/visible maxima. Include all tied tips, visible
   parents of delayed leaves and counter-fork interior anchors; do not replace
   these rules with an arbitrary single-tip shortcut.
2. Reuse validated immutable payloads within a task so the same raw condition is
   not fully validated repeatedly. Preserve schema, identity, content digest,
   native-seed and full behavioral checks at the trust boundary. Current fresh
   disk studies validate in `study`, `ConditionStore.save` and `analyze`; reused
   conditions are also checked multiple times.
3. Stream bounded batches of task outputs. Current `run_sweep` preflight retains
   complete analyzed studies in `prepared`, including deep-copied raw conditions;
   it then accumulates all repetition/terminal rows before export. This is not
   a bounded-memory implementation for 250,170 tasks. Store baseline/conditional
   provenance once and reference it, without duplicating full ledgers across
   aggregate/repetition exports.

No optimization was implemented. In particular, no pruning of fork history,
weakening of validation, smaller grid or smaller horizon was introduced.

### 30,000 blocks and full-grid feasibility

The endpoint and policy semantics support a 30,000 reference-height target; no
new semantic cutoff at that height was found. **Operational usability at that
scale has not been established**, since no 30,000-block native benchmark was
authorized or run in this audit. The persistent full-grid runner as presently
structured should not be treated as production-ready for any policy.

For scale illustration only, a quadratic continuation of the 500-block engine
medians to 30,000 multiplies by 60² and gives roughly **169–235 seconds per SC
run**, before validation, serialization, study aggregation or storage. This is
not a forecast: the grid spans untested powers/gammas/member counts, and the
measured tiny sample is insufficient for extrapolation. Applying even 170 seconds
to 159.6 million runs is about 860 serial core-years before those overheads.
A separate linear-size illustration puts the observed 0.43–0.57 MB checkpoints
near 26–34 MB at 30,000; applying that size uniformly would be multiple petabytes.
Actual compression, sharing, mix of conditions and costs are unmeasured.

Ignore was roughly 1.39× counter k=1 and selfish 1.26× at the tested SC point.
These do not justify different scientific grids. They do justify bounded-memory
execution, cost-aware scheduling and separate pilot calibration after common
scanning/storage fixes. Higher coalition powers and up to six members remain
unprobed, so no full-grid feasibility certification is possible for any rule.

## 5. Shared baseline reuse

The current validated v2 condition store can compute H and S0 once per matched
network/environment, ordered population, seed/repetition and horizon. Its inactive
identity includes neither punishment rule nor counter k. Tests confirm immutable
baseline-file bytes and identical baseline references across counter k=1/2/3,
ignore and selfish. A two-member, two-repetition, horizon-12 disk fixture executes
12 conditions for the first variant and eight for each of the other four:
**44 instead of 60**. No checkpoint provenance was relaxed.

For r variants, baseline work falls from 2r to 2 per environment/repetition:
**66.7% baseline-only savings for three rules, 80% for five k/rule variants**.
For one nonempty coalition with n>=2 members, the independent count is r(n+4),
and the shared count is 2+r(n+2). Savings are 2(r−1). For n=2…6, total-run savings
are 22.2%…13.3% for three variants and 26.7%…16.0% for five. With one member, the
leave-one-out result is already S0, so independent/shared counts differ from the
n>=2 expression; savings are 33.3% for three variants and 40% for five.

Applying only arithmetic to the existing 20-repetition scope artifact—without
creating a persistent production configuration—gives:

| Hypothetical identical grid | Independent runs | H/S0 reuse saves | Remaining runs | Total-run saving |
| --- | ---: | ---: | ---: | ---: |
| Three rules, one counter k | 119,802,600 | 20,013,600 | 99,789,000 | 16.71% |
| Counter k=1/2/3 + ignore + selfish | 199,671,000 | 40,027,200 | 159,643,800 | 20.05% |

This uses 250,170 configurations and 39,934,200 represented runs per variant.
The common H/S0 store holds 10,006,800 baseline runs for that hypothetical grid.
Five-variant remaining nominal work is 4,789,314,000,000 reference-height units
at 30,000; three-variant work is 2,993,670,000,000. These are scope counts, not
measured completed work or runtime estimates. Historical petty-v4 baselines
cannot provide these persistent-v2 baselines, including at lambda zero.

## 6. Recommendation and validation status

Keep the intended k={1,2,3}, scientific grid, 20 repetitions and 30,000-block
horizon unchanged while resolving the conformance detail and addressing the
shared execution bottlenecks. The three persistent policies can use one common
environment/population grid and paired shared baselines. After behavior-preserving
optimization, use separately authorized bounded scaling pilots to set worker,
memory and storage budgets before planning full production execution.

Copying the numeric grid is distinct from copying a scientific admission claim:
the existing grid is filtered by the vanilla Eyal–Sirer analytical authorization.
That existing filter can define a deliberately selected comparison domain, but
this audit does not establish that it proves profitable persistent-v2 S0 at every
selected point. The baseline/publication/endpoint model differs. Revalidate that
interpretation before using the filter as a persistent-model profitability claim;
do not silently alter the current grid or its authorization configuration.

For a strict four-policy experiment, implement and validate petty on the common
persistent network in a future task. Continue treating the existing petty sweep
as its own model's experiment. This audit leaves that running experiment alone.

Validation: the full local suite finished with **842 passed, 9 xfailed in 51.86
seconds**. The 24 new focused audit tests pass; the nine expected failures remain
the historical-v1 baseline invariance audit. The callback-gap reproductions pass
by asserting the observed mismatch; they are evidence of the gap, not claims
that it conforms. Runtime/configuration source hashes are unchanged. Only the
audit program, audit tests and two new audit documents/evidence files were added.
