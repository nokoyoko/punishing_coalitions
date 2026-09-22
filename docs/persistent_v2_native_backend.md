# Native persistent-v2 condition backend

The Python implementation remains the scientific reference. The native backend is
an explicit execution choice for a fresh study; it does not change the experiment
design, stochastic model, validation selection, or historical records.

## Condition boundary

`punishment_sim/native/persistent_v2.cpp` implements petty, counter-fork k=1/2/3,
ignore/ostracism, and independent selfish counter-mining. The same kernel handles
H, S0, HF, SC, and every member leave-out. H/S0 retain the common baseline identity.

Python computes the original condition identity and actual repetition seed,
constructs the existing three `CommonRandom` streams, and passes their MT state
and position into C++. The native implementation uses the same tempering and
53-bit float conversion. It does not seed a different generator. Python also
supplies the original miner weights, including the oceanic residual.

The condition call owns the block tree, binary-lifting ancestry index, public and
private frontiers, visibility window, punishment state, independent private
actors, publication/reaction rounds, rewards, and endpoint construction. The
production discovery loop makes no Python calls. Bulk scientific hashing uses
the existing Python/OpenSSL SHA-256 implementation through the C API.

Python retains policy selection, compact-record validation, producer/receipt
wrapping, SQLite persistence, study orchestration, and cross-condition statistics.
The new backend does not change confidence intervals, paired CRN differences,
scientific classifications, or the analytical authorization domain.

## Validation and compressed witnesses

The native lightweight checker independently reads the emitted ledger and checks
metadata, ancestry, public/private coverage, publication provenance, canonical
chain/frontiers, independent private states, accounting, payoffs, branch
exposures, boundary/window consistency, RNG consumption bounds, finite JSON, and
the existing reaction risk flags. It does not substitute successful simulation
execution for ledger validation. Python's lightweight checker remains available.

Replay selection uses the existing sampled policy, its original full-core
anchors, deterministic condition hash, and risk rules. The first implementation
retained Python replay; after the ledger-allocation optimization, a matched
128-condition development comparison still achieved only 2.78×. Python replay
used 68.31 of the native path's 114.67 CPU seconds (about 60%).

The resulting second optimization is native ledger replay in `replay.hpp`.
It reconstructs discoveries and publication episodes without calling the mining
`step`, `discover`, `publish`, `selfish_publication`, or `run` methods. It checks
discovery draws, chosen parents, withheld/public discovery decisions, mandatory
and absent releases, simultaneous/cascading rounds, natural-fork draws, rewards,
terminal state, and RNG endpoints. Model operations such as ancestry, policy
helpers, tie selection and reward arithmetic remain shared, as they are in the
Python reference's `PublicReplay`. This is independent reconstruction, not an
independently specified second stochastic model; common helper bugs remain a
reason for the Python/native differential suite.

Every selected native condition undergoes that replay inside the C++ call.
Production returns no raw Python witness, whether selected or unselected. The
runtime identifies `native-independent-ledger-replay-v1` separately from the
unchanged scientific validation levels. Python replay remains available as the
reference, including its bounded DAG adapter for very large stress cases.

Native branch paths and reorganization histories retain endpoint pairs into the
immutable tree. The transient encoding is `persistent-native-witness-dag-v1`.
The existing durable compact schemas and scientific hashes are unchanged:
canonical legacy path bytes are streamed into SHA-256 in bounded chunks. Thus
hashing still costs time proportional to the legacy byte stream, but no expanded
array is retained for every branch or historical reorganization. Temporary path
scratch is bounded by one path. No branch is pruned or treated as finalized.

`persistent_v2_dag.py` independently constructs the same endpoint descriptors
during Python replay. Its explicit `expand_fixture` adapter is for differential tests.
The expanded `native.run` interface is also diagnostic; production uses
`native.execute` and the checked compact-witness interface.

## Backend and provenance contract

Planning accepts `--backend python` (the default) or `--backend native`. The
manifest binds that choice, Python source/runtime identity, all native sources
and headers, the wrapper, compiler/build metadata, Python ABI, and binary SHA-256.
Compiled artifacts have immutable hash-specific filenames. A rebuild is explicit;
a process cannot silently switch its already-loaded extension. A native manifest
cannot resume with a changed binary/source or quietly fall back to Python.

Task IDs, population IDs, condition IDs, repetition seeds, shard ownership,
network version, and model versions do not include the execution backend.
Producer/runtime and study IDs do. The original plan checksum and validation
context remain identical for Python and native plans of the same design.

Native failure stops the shard and writes a signed failure record. Restart refuses
a study with a prior validation failure. Existing compact/checkpoint integrity
checks remain in place. For the `validated_condition` diagnostic hook, native
execution supplies `raw=None`; the verified compact record remains available.

No existing study is migrated or resumed by this work. Historical petty-v4 and
persistent model semantics remain unchanged.

## Bounded host acceptance commands

Run later from the updated checkout on an otherwise idle Kinakuta, using its
existing Python environment and C++17 compiler. No dependency download is needed.
The build uses `-O3 -fno-fast-math -ffp-contract=off` and the matching Python
development headers. These commands are instructions, not remotely executed work.

```sh
.venv/bin/python -m punishment_sim.build_native
.venv/bin/python -m pytest -q tests/test_persistent_v2_native.py tests/test_persistent_v2_native_validation.py tests/test_persistent_v2_native_backend.py
.venv/bin/python -m analysis.benchmark_persistent_v2_native --run --output results/persistent_v2_native_host_acceptance --wall-seconds 3600
.venv/bin/python -m analysis.benchmark_persistent_v2_native --result results/persistent_v2_native_host_acceptance/benchmark.json
```

The destination must be fresh. The benchmark has an external 60-minute wall limit,
never invokes a production dispatcher, and writes condition records under a
benchmark-only layout/record kind. It verifies the 229 completed frozen core
conditions and the previously censored condition before timing the 608-condition
inventory from 19 actual core populations at the 30,000-block horizon.
Conditions run sequentially with paired
backend order alternated. This is not a worker-count comparison or a production
duration projection. Incomplete output is never summarized as a completed speedup.

The legacy Python representation has an explicit 250-million-path-entry memory
guard. Conditions above that bound remain in the native inventory. Their
scientific outputs are checked with independent Python DAG replay and a Python
streaming oracle for the unchanged legacy SHA-256, without allocating the expanded
result. They are explicitly reported as unpaired, and are excluded from the
paired timing ratio. No full-corpus speedup is inferred from that ratio. This
guard changes neither production validation nor scientific parameters.

Full-worker startup, plan enumeration, evidence-file writing, diagnostic path
counting, and downstream statistical aggregation are outside condition timing.
Initialization, simulation, representation/extraction, applicable validators,
authenticated SQLite writes, and backend-specific cyclic cleanup are included.

The local equivalence and performance results below must be assessed separately
from acceptance on Kinakuta's compiler, Python ABI, processor, and filesystem.

## Local result and recommendation

The completed comparison achieved **4.923× whole-condition CPU speedup** on
**607 exact Python/native pairs**, including the actual sampled validation policy
and authenticated SQLite persistence. All 608 native conditions completed. One
larger condition has an independently verified native result but no expanded
Python end-to-end timing under the memory guard; it is excluded from every paired
ratio and subgroup table below. The report therefore records
`COMPLETE_WITH_REFERENCE_LIMITS`, not an unqualified 608-pair result.

This is a strong result under the requested engineering thresholds. The backend
is ready for the bounded host acceptance commands above. A fresh native production
study is recommended **after** that host's compiler/ABI equivalence tests and
bounded benchmark pass. No Linux/Kinakuta performance or production completion
time is inferred from this local macOS arm64/CPython 3.13.3 measurement. Python
remains the default; enabling native execution requires an explicit fresh plan.

The [complete measured evidence](persistent_v2_native_backend_evidence.json)
contains condition identities, exact hashes, attestations, per-condition clocks,
source/binary identities, and the unpaired result. The
[compact summary](persistent_v2_native_backend_summary.json) is generated by the
read-only `--result` command. The earlier
[incomplete development run](persistent_v2_native_backend_initial.json) and
[128-pair Python-replay measurement](persistent_v2_native_python_replay.json)
are retained separately; neither is presented as the final benchmark.

## Equivalence evidence

- **173,430 exactly matching RNG draws**, with exact continuation states, across
  all three existing streams, five seeds (including negative and large seeds),
  and MT twist boundaries. The native kernel imports the Python-initialized state.
- **3,024 complete trajectory fixtures** compare discovery choices, publication
  actions, accepted chains, rewards, terminal/private state, raw results, compact
  records and legacy hashes exactly. They span six rules, cardinalities 2/3/4,
  balanced/skewed weights, H/S0/HF/SC/every leave-out, three seed/repetition cases,
  gamma 0/intermediate/1 and lambda 0/.005/.02 (plus a forced-window stress case).
- Additional step-level fixtures cover explicit ownership, absent/present target
  races, residual actors, petty multiway ties, counter depth/refresh/reanchor/
  supersession, ostracism descendants/multiple roots, multi-block publication,
  simultaneous/cascading independent selfish reactions, terminal private chains,
  and deep reward-reversing reorganization.
- **2,880 lightweight mutation comparisons** and **2,880 full-replay mutation
  comparisons** agree with the Python reference on acceptance/rejection. Extra
  fixtures cover valid diagnostics, Unicode, large integers, nonfinite numbers,
  malformed ancestry, and the compressed-witness adapter. These are differential
  evidence over supported production ledgers, not a claim of formal equivalence
  over arbitrary Python objects.
- A pre-timing pass checked **230 real-core conditions**: 229 frozen reference
  hashes/attestations with byte-identical scientific source files, and the larger
  previously censored condition using independent Python DAG replay and a Python
  streaming hash oracle. All passed before paired timing began.
- Every one of the **607 timing pairs** then matched the full compact result,
  legacy native-result hash and validation attestation exactly (producer identity
  is deliberately backend-specific). The remaining native condition matched its
  independent reference hash and actual-policy attestation.

The fixed inventory comprises every required condition for 19 actual core
populations: one balanced and one skewed choice per cardinality/lambda cell, plus
a gamma-zero control. There are 288 balanced, 288 skewed and 32 control conditions,
all at 30,000 accepted blocks and repetition 0. Common H/S0 results are deduplicated.
The original full-core validation context and 810 anchors are preserved; the
subset does not invent benchmark anchors. This deliberately stratified engineering
sample is not weighted to estimate the complete production sweep's duration.

## End-to-end timing

| Paired scope: 607 conditions | Python | Native |
| --- | ---: | ---: |
| Total CPU seconds | 1,016.764494 | 206.547059 |
| CPU seconds per condition | 1.675065 | 0.340275 |
| Sum of measured condition wall seconds | 1,020.309506 | 207.511802 |
| Whole-condition CPU speedup | 1× | **4.922677×** |

All 608 native conditions together used **242.653878 CPU seconds**
(0.399102 seconds/condition), including the unpaired 36.106819-second stress case.
There is no matching 608-condition Python total.

Replay ran on **98/608 conditions (16.1184%)**, or 97/607 within the paired table.
Across all native conditions, replay reasons included simultaneous selfish
reactions in 95, cascading reactions in 90, and deterministic hash sampling in 4;
these counts overlap. No condition in this subset was replayed because it became
an artificial benchmark anchor. Selection and attestations are unchanged.

| CPU stage, paired conditions | Python seconds | Native seconds |
| --- | ---: | ---: |
| Simulation/event stepping | 408.622 | 40.124 |
| Terminal construction, extraction and serialization | 233.636 | 67.570 |
| Lightweight ledger validation | 144.349 | 68.416 |
| Selected independent replay | 156.613 | 23.553 |
| Compact-record validation | 0.097 | 0.102 |
| Authenticated SQLite persistence | 0.381 | 0.383 |
| Backend-specific cleanup | 72.929 | 2.200 |
| Initialization, selection, boundary and remaining overhead | 0.138 | 4.199 |
| **Total** | **1,016.764** | **206.547** |

Python terminal construction is 64.600 CPU seconds and extraction is 169.036;
native emission combines those operations. Native simulation is now 19.43% of
paired CPU time, emission 32.71%, lightweight checks 33.12%, and replay 11.40%.
Remaining overhead includes parser/result allocation, native call teardown and
small wrapper costs that fall outside the explicit internal stage timers.

## Paired subgroup timing

All tables exclude the single unpaired selfish/m=2/lambda=.02/SC result.
Counts and timing are sums of conditions, not averages of speedup ratios.

| Rule | Conditions | Python CPU-s | Native CPU-s | Speedup |
| --- | ---: | ---: | ---: | ---: |
| petty | 95 | 97.572 | 18.625 | 5.239× |
| counter-fork k=1 | 95 | 111.087 | 28.544 | 3.892× |
| counter-fork k=2 | 95 | 119.394 | 30.699 | 3.889× |
| counter-fork k=3 | 95 | 121.098 | 31.057 | 3.899× |
| ignore | 95 | 159.018 | 30.576 | 5.201× |
| selfish | 94 | 376.454 | 61.051 | 6.166× |
| shared H/S0 | 38 | 32.141 | 5.995 | 5.361× |

| Cardinality | Conditions | Python CPU-s | Native CPU-s | Speedup |
| --- | ---: | ---: | ---: | ---: |
| 2 | 155 | 351.304 | 57.088 | 6.154× |
| 3 | 224 | 295.308 | 64.535 | 4.576× |
| 4 | 228 | 370.152 | 84.924 | 4.359× |

| Lambda | Conditions | Python CPU-s | Native CPU-s | Speedup |
| --- | ---: | ---: | ---: | ---: |
| 0 | 224 | 330.515 | 73.477 | 4.498× |
| .005 | 192 | 425.552 | 74.244 | 5.732× |
| .02 | 191 | 260.698 | 58.826 | 4.432× |

| Condition type | Conditions | Python CPU-s | Native CPU-s | Speedup |
| --- | ---: | ---: | ---: | ---: |
| H | 19 | 12.837 | 2.048 | 6.267× |
| S0 | 19 | 19.304 | 3.947 | 4.891× |
| HF | 114 | 129.615 | 27.291 | 4.749× |
| SC | 113 | 255.533 | 47.909 | 5.334× |
| SC leave-out | 342 | 599.475 | 125.352 | 4.782× |

## Pathological selfish conditions

The known condition
`4dc4dc72b090112b003c112144c20cbbc07618f29318ca48faa7c93b49827574`
has 77,776 unique blocks, 17,611 terminal branches and **44,034,951 repeated
terminal path entries**, plus 29,251,518 removed-block entries in 17,414
reorganizations. Its unchanged raw-result hash is
`233b2dfab004ef76251bc947bf3f0999fd2d3a13e71bdc1bfa1cda26630fb62d`.

Its final matched timing is **76.260157 Python versus 5.798671 native CPU
seconds (13.151×)**. Native simulation uses 0.459172 seconds, emission 4.271927,
lightweight checks 0.247445, and selected replay 0.803261. Production transfers
only the 7,524-byte compact result to Python, with no raw witness. Internally it
retains 52,439 path descriptors and the unique block tree, not the repeated path
arrays. The original historical hash contract is preserved by streaming.

The larger condition
`ae86482dcdf074dfc767ea4be85e4890b52797636c47de601d0daf80baf89d45`
has 138,004 blocks, 24,964 terminal branches and **294,872,129 terminal path
entries**, plus 208,414,279 removed and 208,439,205 added entries. Its independent
reference hash is
`b45263a1c3d23e37809dcff5b8b5f2cc30fa5f92f4769d44dcecdaef895b6ad8`.
Python DAG replay (213.952 CPU seconds) and Python streaming hashing (72.590)
verified it without constructing expanded arrays. Those are diagnostic oracle
costs outside the benchmark timing, not a Python end-to-end measurement.

Its measured native condition completes in **36.106819 CPU seconds**: 3.361306
simulation, 28.375910 emission, 0.399366 lightweight checks and 3.942899 replay.
It retains 74,816 path descriptors and returns a 7,569-byte compact record with no
raw Python witness. Streaming the unchanged legacy bytes remains its dominant
cost. Changing that durable hash representation could reduce this cost further,
but is not required for the measured backend and was not done here.

## Tests, invariance and changed files

The native trajectory/validation/backend suite passed **3,126 tests**. The full
local suite passed **4,726 tests, with 9 expected failures**, in 260.14 seconds.
The two benchmark-oracle/report tests also pass. `git diff --check` and Python
compilation checks pass. All simulations executed for this work were bounded
local equivalence, test or benchmark fixtures.

Backend integration tests compare Python/native plans, condition records and
restart behavior. The scientific design, population/condition/task identities,
repetition seeds, CRN pairing, shard ownership, SQLite plan hash, validation
context and model/network versions remain identical. Native runtime/producer and
study identity differ deliberately. Changed backend/header/binary bindings fail
manifest validation even when an outer checksum is recomputed; tampered binaries
are rejected before loading. Validation failures are signed, fatal, and never
silently retried as Python conditions. Python reference regeneration of a native
record is also tested.

Files added for this backend:

- `punishment_sim/native/{persistent_v2.cpp,path_emission.hpp,json_value.hpp,lightweight.hpp,replay.hpp}`:
  kernel, bounded path/hash emission, ledger parser, lightweight checks and replay.
- `punishment_sim/{build_native.py,persistent_v2_native.py,persistent_v2_dag.py}`:
  explicit build/provenance, Python boundary and independent reference DAG adapter.
- `analysis/{benchmark_persistent_v2_native.py,persistent_v2_reference_witness.py}`:
  bounded actual-core comparison and independent Python streaming-hash oracle.
- `tests/test_persistent_v2_native{,_validation,_backend,_benchmark}.py`:
  equivalence, adversarial validation, backend control-plane and evidence tests.
- This document and `persistent_v2_native_backend_{evidence,summary,initial}.json`,
  plus `persistent_v2_native_python_replay.json`.

Existing files updated for this backend are `persistent_v2_checkpoint.py`
(optional reference DAG representation), `persistent_v2_compact.py` (runtime
identity/reference rerun), `persistent_v2_shards.py` (backend selection and strict
failure/provenance handling), `pyproject.toml` (package native sources),
`tests/test_persistent_v2_51pct_evidence.py` (control-plane source allowlist),
`tests/test_persistent_v2_quick_benchmark.py` (inventory checks), and `README.md`.
The earlier serializer/profile/prototype work already present in the working
tree is preserved; it is separate from these backend additions.

No production simulation or production dispatcher was launched. No SSH,
Kinakuta/remote job, `/xtra` access, running-study modification, historical record
rewrite, or production configuration change was performed.
