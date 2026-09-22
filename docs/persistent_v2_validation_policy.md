# Persistent-v2 production validation and measured concurrency

The future core/extension configurations now explicitly select `sampled`
validation. The scientific simulation and statistical reductions are unchanged.
This control-plane change introduces a new manifest/compact-record contract;
it does not import or relabel records from an existing production study.

## Policy contract

```json
"validation_policy": {
  "mode": "sampled",
  "salt": "persistent-v2-production-audit-2026-09",
  "sample_per_million": 10000
}
```

Normalization adds `version: persistent-production-validation-v1`. A design
without a policy defaults to `full`. For debugging, set `mode` to `full` in a
fresh design. Both modes run the same inexpensive checks before committing each
new condition; `full` additionally runs the existing complete native validator
every time. `sampled` runs that same validator for the selections described below,
while the full ledger remains in memory. No scientific RNG draw is used by the
policy. No checks are skipped just because a condition has a valid checksum.

The full validator reconstructs publication/policy decisions and random choices
from the actual ledger. It can detect a structurally consistent but invalid
trajectory that lightweight accounting would accept. Test fixtures cannot check
every production trajectory; seeds describe reproducibility, and checksums/HMACs
describe authenticity/integrity, not correctness of the trajectory. Full replay
still shares native helpers with the engine and is not an independent proof of
the scientific model. Sampling deliberately forgoes trajectory certification on
the lightweight-only runs; their metadata states that limitation.

### Every fresh condition

1. Reconstruct expected population/condition/model/strategy/flag/coalition/rule,
   repetition and actual seed identity from the planned task. Check successful
   native completion, recording mode, absence of scripted discoveries, integer
   event/block counts and the required accepted-block horizon.
2. Scan the ledger: unique contiguous discovery IDs, valid owners, earlier
   parents, consistent heights/flags, exact public/hidden coverage, publication
   batches and ordering, and parent-before-child publication. Check canonical
   chain links/length/reference tip and maximum public height.
3. Check public/private frontier sets and selfish actor membership; private and
   abandoned ownership, disjointness and complete hidden-block coverage; private
   chains, bases, tips, heights/leads and released-block lists; empty reaction queue.
4. Recount discovered, accepted, orphaned and unresolved blocks by actor. Check
   actor/global conservation, hash power/role identity, accepted rewards,
   payoff arithmetic and normalized revenue.
5. Check terminal alternative-branch paths, common ancestors, exposed canonical
   blocks/rewards and boundary maximum; ignore-policy eligible frontier paths
   (including eligible interior prefixes); pending visibility-window endpoint
   and unresolved-boundary presence. Compact checks retain conservative payoff
   bounds and exact downstream terminal summaries.
6. Check discovery draw count, tie/natural draw-count bounds, nonnegative integer
   counters, reaction diagnostics and finite JSON values throughout the raw
   result. These are bounds/accounting checks, not RNG stream replay.
7. Extract the same sufficient scientific record; check compact schema, producer,
   identity, explicit validation attestation, horizon, conservation/payoffs,
   terminal summary, bounds, trajectory hashes and finite values before commit.

Ledger scans do **not** reconstruct fork choice, punishment decisions, natural
fork draws, release plans or the full policy trajectory. Existing runtime
invariants remain enabled. Existing manifest checksum, JSON normalization,
source/Python fingerprints, SQLite integrity, plan content hash, immutable writes,
payload checksums, HMAC receipts, baseline references and strict resume/merge
reconstruction remain mandatory. Authenticated resumed results are checked under
their original policy; resume does not remine/replay them.

### Deterministic selection and coverage

The base sample hashes canonical JSON of
`[policy_version, salt, "condition-sample", condition_id]` using SHA-256. Select
when `integer_hash * 1_000_000 < sample_per_million * 2**256`. The configured
10,000-per-million rate is approximately 1%, without rounding or RNG consumption.
Shared H/S0 IDs contain no rule or k, so their decision is independent of the rule
that reaches the baseline first.

During planning, stratify the **actual feasible populations** by:

- exact cardinality, gamma and lambda;
- attacker power below .20, .20–below .30, or at least .30;
- coalition total below .20, .20–below .40, or at least .40;
- composition: equal, otherwise max/min at least 4, otherwise moderate.

For each occupied stratum, select the minimum
`(SHA256([version, salt, "stratum-anchor", population_id]), population_id)`.
At every selected population, force every native required condition for every
configured rule at zero-based repetitions 0 and 5 (public repetitions 1 and 6).
Thus both fixed phases cover petty, counter-fork k=1/2/3 separately, ignore,
selfish, H, S0, HF(C), SC(C), and each leave-one-out. The core plan has **810**
anchor populations; extensions 5 and 6 each have **270**. Empty/infeasible strata
do not create scientific tasks. Each manifest load recomputes these anchors from
the existing plan while checking its hash. Enumeration, sharding, worker order,
time and restart order cannot change the selections.

Additional deterministic targeting inspects recorded selfish reaction frames:
more than one decision in a frame, or more than one reaction round in a discovery,
forces full replay. This captures simultaneous releases/abandonments and cascading
publication paths without invoking a policy helper or consuming random values.
The maximum counts and selection reasons are retained in the compact record.
These overrides depend on the recorded path; the baseline hash sample does not.

The regression suite continues to exercise seed-84 propagation/private-prefix
cases, counter-fork defended-depth/refresh/supersession, delayed visibility,
petty multiway ownership, ignore ancestry and independent selfish actors. New
native fixtures cross-check lightweight/full acceptance for every rule and
zero/positive lambda, and explicitly exercise simultaneous/cascading reactions.
The anchors cover the relevant parameter regimes; they do not promise that every
possible rare trajectory occurs in the finite sample. The actual replay fraction
is **not capped at 1%** and can be materially higher, especially for selfish rules.

### Metadata, failure and historical records

The manifest layout is `persistent-compact-shards-v2-2`; compact records use
`persistent-scientific-condition-v2-compact-2`. `study.json` binds the normalized
policy, salt and exact anchor map into `study_id`. Its existing durable JSON
normalization remains intact. Each compact record contains:

```text
validation.policy_sha256  SHA-256 of the whole manifest validation context
validation.level         lightweight-ledger-v1
                         OR lightweight-ledger-plus-native-replay-v1
validation.replay_reasons full_policy / hash_sample / stratum_anchor / risk:...
validation.risk_flags     recorded simultaneous/cascading reaction evidence
```

The old `complete-native-ledger-and-rng-v2` string is not used. Compact readers
recompute the required level and reasons from identity, bound policy/context and
recorded diagnostics; merge/resume cannot relabel lightweight records as full.
This attestation is authenticated producer metadata, not a proof independent of
the producer and receipt keys.

Any fresh-validation exception stops the worker. Before propagating the error,
the store commits an authenticated `validation_failure` marker and attempts to
save the raw ledger under `validation_failures/<condition_id>.json`. Malformed
nonfinite JSON may prevent the diagnostic dump, but the marker remains. Resume,
analysis and merge refuse a shard with that marker. No automatic retry, downgrade
or discard-until-success path exists. Investigate the failure before creating a
fresh study.

**The presently running old-contract study cannot be resumed/imported with this
code.** Full replay in the old records is stronger behavioral evidence than a
lightweight check, but does not satisfy the new source, schema, context and receipt
contract. No compatibility exception or migration was added. Preserve that study
and its exact code separately; a future sampled production study needs a fresh
directory/plan. No current production files or workers were modified here.

Unchanged: mining transitions, punishment semantics, gamma/natural-fork behavior,
task/population/condition IDs, repetition seeds and RNG streams, CRN pairing, ten
repetitions, statistical estimators, shard ownership and all model/network versions.
Only control metadata, validation policy, runtime fingerprint, study ID and receipt
namespace change. Exact plan/identity audits and full-vs-sampled native/result
comparisons check these distinctions.

## Concurrency benchmark

Reported Kinakuta observations (user supplied, no remote verification): 16 physical
cores, 32 logical CPUs, 28 worker processes, CPU-bound with negligible aggregate
I/O wait, about 1,923 Phase-I repetition records/hour. Core Phase I contains
3,799,980 repetition records and 20,266,560 unique conditions. Holding that record
rate constant gives **82.34 days**; an ideal removal of 49% of total cost still
gives **41.99 days**, versus the old ideal-28-worker 13.89–16.85-day illustration.
An early, nonuniform workload is not a defensible extrapolation of the whole grid.
No new runtime estimate follows from those arithmetic comparisons.

`analysis.benchmark_persistent_v2_concurrency` provides `--describe` (plan only)
and an explicit `--run`. Its fixed configuration selects 108 populations:
cardinalities 2/3/4; lambda 0/.005/.02; authorized (attacker,gamma) pairs
(.35,0), (.30,.5), (.20,1); coalition totals .10/.50; balanced and skewed
composition extremes; all six rules. It retains native horizon 30,000, seeds,
detector settings and reducers, and executes the first five repetitions.

Every trial runs the identical **17,280 unique conditions / 3,240 repetition
records**. Each uses the same 216 fixed shard work units; the worker pool alone
changes between 8/16/24/28. H/S0 reuse remains native. Each condition's native
result hash must match across every trial/policy; selections must also match
across all trials of the same policy. Failure aborts the benchmark and marks its
report `FAILED`. Timing trials never resume a used destination.

Run on an otherwise idle host after pausing/stopping existing production workers
through their existing job controls. Keep interpreter, hardware, configuration,
CPU governor and any affinity settings constant. Do not benchmark concurrently
with the old production sweep. Planning is outside the wall timer; process start,
manifest/SQLite checks, scheduling and commits are inside. A second repeat reverses
both concurrency and policy order to expose order/thermal/cache effects.

`benchmark.json` reports completed conditions, wall seconds, aggregate conditions/s,
planning time, summed worker CPU seconds, average busy cores, worker-capacity and
logical-CPU utilization, actual replay fraction/reasons, and total/replayed counts
by rule/k/cardinality/lambda/gamma/attacker power/condition type. Phase timers
separate mining, lightweight checks, sampled replay, full-policy replay,
extraction, compact checks, aggregation and serialization/writes. Summed worker
times are not wall times. Worker CPU figures exclude parent/import startup costs
and do not measure host I/O wait; `pidstat`/`mpstat` can supplement them if installed.
The benchmark does not infer physical core count from logical CPUs.

Compare measured aggregate throughput and CPU utilization across worker counts;
do not multiply a single-worker rate by 28. Compare policy timings within the
same worker-count trial. This deliberately broad but small workload has dense
forced strata: approximately one forced repetition out of five per anchor,
before risk overrides. Report its actual replay fraction; it is not an estimate
of the production grid's replay fraction. Its high-power cases and boundary cost
also preclude treating the average as a full-grid forecast without workload weighting.

One repeat of four worker counts and two policies means eight trials, **138,240
conditions** total. Two repeats double that work. These are operator-launched
30,000-block benchmark runs, not quick tests. None were run for this change.

## Deployment and benchmark commands (supplied, not executed)

The local deliverable `results/persistent_v2_validation_deployment/` contains
`persistent-v2-validation-source.tar.gz` and its `.sha256` file. It includes
reviewed source/config/tests/docs and `SOURCE_SHA256.json`, but no results,
checkpoint databases, receipt keys, virtual environment or Git metadata.
Transfer those two files by your normal mechanism into the **existing remote
checkout root**. The commands below run there in Bash and create a separate
sibling source directory; they do not edit the code used by old workers.
The complete local suite also reads historical result tables that are deliberately
excluded from the source bundle. The deployment check below uses the self-contained
persistent-v2 suite, including policy, provenance and benchmark fixtures.

```bash
set -euo pipefail
pc_old_root="$PWD"
pc_python="$pc_old_root/.venv/bin/python"
pc_bundle="$pc_old_root/persistent-v2-validation-source.tar.gz"
pc_deploy="${pc_old_root}-validation-policy-$(date -u +%Y%m%dT%H%M%SZ)"
test -x "$pc_python"
sha256sum -c persistent-v2-validation-source.tar.gz.sha256
test ! -e "$pc_deploy"
mkdir -- "$pc_deploy"
tar -xzf "$pc_bundle" -C "$pc_deploy"
cd "$pc_deploy"
export PYTHONPATH="$pc_deploy"

"$pc_python" - <<'PY'
import hashlib, json
from pathlib import Path
for name, expected in json.loads(Path('SOURCE_SHA256.json').read_text()).items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
import punishment_sim
assert Path(punishment_sim.__file__).resolve().parent == Path.cwd()/'punishment_sim'
print('Verified deployed source and import location')
PY

"$pc_python" -m pytest -q tests/test_persistent_v2*.py
"$pc_python" -m analysis.benchmark_persistent_v2_concurrency --describe
```

After reviewing the inventory and making the host idle, run the following in the
same shell. This executes **only the fixed benchmark**, with a fresh output tree.
Use `--trials 2` for the additional reversed-order repeat if the initial bounded
comparison justifies that cost; never reuse a timing destination.

```bash
pc_benchmark="results/concurrency-validation-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$pc_benchmark"
mkdir -p results
lscpu > "${pc_benchmark}.host.txt"
"$pc_python" -m analysis.benchmark_persistent_v2_concurrency \
  --run \
  --config configs/persistent_v2_concurrency_benchmark.json \
  --workers 8 16 24 28 --modes full sampled --trials 1 --rep-end 5 \
  --output "$pc_benchmark" 2>&1 | tee "${pc_benchmark}.log"
"$pc_python" - "$pc_benchmark/benchmark.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
assert report['status'] == 'COMPLETE'
print(json.dumps(report['summary'], indent=2))
PY
```

No production-launch command is included. Choose the future production concurrency
and confirm the fresh policy/plan only after reviewing these measurements.

## Local verification

The full local suite passed: **1,106 passed, 9 expected historical-v1 failures**
in 104.86 seconds. Only authorized local fixtures mined. New tests cover
deterministic/order-independent selection, shared baselines, all cardinalities
2–6 and all condition/rule types, runtime/manifest policy binding, anchor integrity,
metadata enforcement, native/light agreement and corruption, fatal failure with
no retry, strict resume/merge, identical scientific records/reducers across modes,
and a tiny process-pool benchmark at two concurrency levels. Existing manifest
round-trip/key/hash protections and scientific identity fixtures pass unchanged.
Exact scope enumeration performed no mining; native production plan hashes and
counts remain unchanged. Historical performance evidence was preserved and marked
as unsuitable for forecasting this new policy. After the final configuration and
projection assertions, the focused policy/manifest/cardinality/concurrency suite
also passed **64 tests**. A fresh actual core plan loaded successfully with mining
construction forbidden: 126,666 populations, 40,533,120 conditions, 810 anchors,
and unchanged native plan SHA-256
`94777cf6121c6f8c49d2b37d90b5f2f9681e551cc82dbc25ebc2813c91d4379e`.
The benchmark `--describe` path performed no mining. Whitespace and shell syntax
checks, plus source-bundle hash verification, are recorded with the deliverable.
