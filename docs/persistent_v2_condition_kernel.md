Persistent-v2 condition-kernel investigation — local measurements, 22 September 2026

The earlier event-loop-only calculation was too narrow to decide whether a C++ condition kernel is worthwhile. The corrected scope includes state management, reporting and direct compact extraction. Moreover, ledger checking and independent replay are computational work that could also be native; retaining the current Python validators is a conservative implementation choice, not a language constraint.

An opt-in native H/S0/petty prototype now exists. It preserves exact RNG and native outputs, includes direct compact extraction, and continues to use the unchanged Python validators. It is not registered with production dispatch. No counter-fork, ignore or independent coalition-selfish implementation has been added to it.

All measurements below are bounded local diagnostics on CPython 3.13.3, macOS arm64, using Apple clang 17 for C++. They do not estimate Kinakuta throughput or production duration. No production sweep, SSH, remote job, Kinakuta access, `/xtra` access, or modification of a running study occurred.

1. **Post-fix profile and coverage.**

The same 230-condition diagnostic inventory was used: actual core-plan identities from 19 populations, six rule variants, cardinalities 2/3/4, lambda 0/.005/.02, balanced/skewed compositions, gamma endpoints and intermediate values, H/S0, HF, SC and member leave-outs. Every condition uses the native 30,000 accepted-block horizon, actual repetition-0 seed 51000, and the original full-core sampled-validation context. No benchmark-specific anchors were introduced.

229 conditions completed. One balanced selfish SC condition at m=2, target .29, coalition (.24,.25), gamma .5, lambda .02 exceeded the 35-second trajectory budget and is **censored**, not counted as completed. Its ID is `ae86482dcdf074dfc767ea4be85e4890b52797636c47de601d0daf80baf89d45`. The former 44M-path outlier completed. This is an unweighted diagnostic sample, with a potentially expensive censored tail; these percentages are not population-weighted production estimates.

CPU time comes from separate `process_time()` stage timers. cProfile repeats do not contribute to the stage totals. The complete-condition clock includes initialization, validation, authenticated storage and measured deletion; diagnostic-only structural counting is subtracted. It does not force collection of cyclic engine objects after every condition. The later paired prototype benchmark does charge explicit cyclic cleanup to the originating backend. Full-worker plan startup and downstream cross-condition statistical aggregation are outside both sets of condition timings.

| Measured stage | CPU seconds | Total CPU | Boundary classification |
|---|---:|---:|---|
| Simulation/trajectory | 189.058 | 46.011% | A: native state and event processing |
| Terminal/native result construction | 29.690 | 7.226% | A: construct from native structures |
| Compact extraction and hashes | 64.321 | 15.654% | A: direct native emission/extraction |
| Lightweight ledger validation | 55.918 | 13.609% | A in a broader port; retained in Python in this prototype |
| Independent native replay | 70.903 | 17.256% | A in a broader port; retained in Python in this prototype |
| Python initialization/seeding | .018 | .004% | B |
| Validation-policy selection | .010 | .002% | B |
| Compact/envelope consistency check | .036 | .009% | B |
| SQLite/HMAC persistence | .138 | .034% | B |
| Measured Python object cleanup | .766 | .186% | B, conservatively retained |
| Remaining timer/orchestration work | .036 | .009% | B |
| **Total** | **410.895** | **100%** | |

32/229 conditions actually replayed (13.97%), costing 70.903 CPU seconds: 31 were risk-selected selfish cases and one was hash-selected. Simultaneous and cascading risk reasons overlap. The full-plan anchor list was preserved, but these selected populations are not anchors. The observed replay fraction is not an estimate of the entire production design.

The trajectory row includes block/tree mutation, public/private frontier maintenance, ancestry indexes and queries, actor draws, gamma/tie handling, natural-fork windows, punishment state, independent selfish actors, publication/reaction rounds, reorganization traversals and reward accumulation. None of those operations requires per-event Python crossings. Terminal construction includes explicit paths, block conversion, private-state summaries, exposed rewards and boundary diagnostics. Extraction includes canonical JSON and scientific hashes; it need not first build nested Python objects.

The following are the largest **self-time** consumers within each separately instrumented stage over the 59 prescribed profile conditions. Inclusive times overlap and are not summed. These function percentages describe the instrumented subset, not an allocation of the whole 229-condition total; in particular the 44M-path case is outside that 59-condition subset.

| Stage | Top consumers, self % within stage |
|---|---|
| Trajectory | `AncestryIndex.add` 8.13%; `step` 6.94%; `SelfishActors.on_publication` 4.39%; `sum` 4.30%; `publish` 4.15%; `sorted` 3.97% |
| Terminal | `_asdict_inner` 33.76%; `dataclasses.fields` 15.43%; `getattr` 7.68%; terminal function 7.29%; dataclass field generator 6.67% |
| Lightweight | JSON `iterencode` 40.23%; ledger checker 38.86%; `require` 4.83%; `json.dumps` 2.25% |
| Replay | `_validate_run` 12.85%; ancestry indexing 7.91%; JSON `iterencode` 4.73%; `_asdict_inner` 4.65% |
| Extraction | JSON `iterencode` 87.82%; SHA-256 5.15%; `terminal_summary` 2.14%; UTF-8 encoding 1.74% |

The saved trajectory call-rate denominator was 1,770,000 nominal blocks; actual accepted blocks were 1,770,001 because of a final publication overshoot. Timings and percentages are unaffected. The script now uses the actual accepted-block count for future call-rate tables.

2. **Movable scope and Amdahl calculations.**

There are two distinct scope calculations. They must not be conflated:

- **Condition generation plus extraction, keeping the unchanged Python scientific validators:** A = **68.891%**, B = **31.109%**. This covers the simulation, terminal construction and compact extraction rows. It is the conservative prototype scope. Its B includes independently implemented Python validation by choice.
- **Literal “could live in a native condition call” scope, including separately implemented lightweight checking and independent replay:** A = **99.756%**, B = **.244%** at the measured stage granularity. A native checker must retain all existing checks and a separate replay algorithm; having the simulator certify its own output would not satisfy this scope. The validators were **not** ported here. Tiny identity/provenance operations inside validator timers have not been split out, so this is a stage-level architectural ceiling, not a precise port-cost estimate.

Python planning, identity/seed preparation, policy selection, producer/envelope checks, SQLite/HMAC and cross-condition statistics reasonably remain outside the native kernel. Cross-condition statistics were not measured here, and are not assigned fictitious zero whole-sweep cost. Returning a Python validation witness also creates a **new** conversion cost absent from the all-Python profile; the prototype measures it explicitly.

For existing fraction A and acceleration s, `speedup = 1 / ((1-A) + A/s)`:

| Acceleration of the entire A fraction | Generation/extraction A=68.891% | Broader computational A=99.756% |
|---|---:|---:|
| 2× | 1.525× | 1.995× |
| 5× | 2.228× | 4.952× |
| 10× | 2.632× | 9.785× |
| Infinite | 3.215× | 409.326× |

The very large last architectural number only says little of this *condition-stage* CPU is intrinsically orchestration. It is not an achievable-speed prediction. Both columns omit newly introduced native/Python conversion cost; the broader column additionally assumes an unimplemented, independently validated native verifier. Neither is a production-duration estimate.

Even the conservative column exceeds a 3× ceiling, so a minimal prototype was justified. Reaching 3× with that unchanged B would require approximately 31× acceleration of **all** generation/extraction, before conversion overhead. Accelerating stepping alone cannot establish this. A ≥3× whole-condition improvement remains architecturally plausible, but the actual prototype measurement below determines what has been demonstrated.

3. **What the 44,034,951 entries mean.**

The expensive condition is selfish SC, target .31, coalition (.06,.38), gamma .5, lambda .005, seed 51000; ID `4dc4dc72b090112b003c112144c20cbbc07618f29318ca48faa7c93b49827574`.

It discovers **77,776 unique blocks**, leaves **17,611 terminal branches**, and has a longest alternative path of **13,222 blocks**. Each `alternative_branches[i].path` lists the block IDs from that leaf's first canonical ancestor, exclusively, to its tip, inclusively. The measured total is:

`sum(len(branch.path)) = 44,034,951`.

Equivalently, each noncanonical block is counted once for every retained terminal leaf below it. A deep reorganization can make a formerly canonical prefix noncanonical; many historical side leaves then share that long prefix. The complete-frontier contract retains old public leaves and hidden/abandoned private leaves, including branches well behind the current maximum. Repeating their ancestor paths produces tens of millions of references from fewer than 78,000 unique blocks. These are neither 44M discoveries nor 44M alternative terminal tips.

There are also **29,251,518 removed-block references in 17,414 reorganization records**. Terminal-path and removed-block list slots alone imply approximately **559 MiB** of pointer storage on a 64-bit interpreter, before list over-allocation, block objects, dictionaries, other lists and JSON buffers. This is a structural lower bound, not a measured peak-RSS result.

The tree, ownership, publication history, live states and unresolved frontier contain scientific information. The repeated path vectors are a **redundant representation**, not additional scientific state. They are not needed as repeated arrays to execute the event loop or calculate accepted rewards. Endpoint/ancestor data and owner-prefix counts can reproduce the exposed-reward and path-length summaries. However, explicit paths and reorganization lists are currently required by native witness validation, replay comparison, canonical scientific hashes and diagnostic output. They are not merely optional debug traces that can be deleted without changing a contract.

The serializer fix changes `frontier_blocks` accumulation to a union of IDs and calls `asdict` once per emitted block. It avoids repeated conversion and allocation of temporary block dictionaries that were immediately overwritten. **It does not reduce the final path vectors or reorganization lists.** `_branch` still walks and materializes each path, and validation and hashing still scan the expanded witness. No scientific branch-pruning assumption was introduced.

Fresh post-fix CPU seconds for this one condition:

| Stage | CPU seconds |
|---|---:|
| Trajectory | 21.139 |
| Terminal construction | 3.188 |
| Lightweight validation | 8.318 |
| Replay | 33.266 |
| Extraction | 8.322 |
| Complete condition | 74.289 |

Terminal construction, lightweight checks and extraction together take 19.829 seconds (26.69%); replay adds 33.266 seconds, including both independent state reconstruction and reporting/checking. These are not all pure path-materialization costs, but they show that state representation and its repeated processing remain major costs. The previous post-fix timing was 77.42 seconds; the new value is a fresh measurement, not a second algorithmic improvement.

A native parent/owner vector can avoid most intermediate Python state. Streaming canonical paths/hashes or representing shared prefixes once could also avoid large materialized lists while retaining exact values. Such a representation must be checked against the current independent contract. The prototype still emits the full raw witness and decodes it for unchanged Python validators, and it does not support this coalition-selfish rule; it does **not** claim to solve the 44M condition.

4. **Fresh matched historical comparison.**

The 57 real H/S0/petty-SC conditions were each run through petty-v4, v2 with the original serializer, and current v2. Backend order rotates across conditions. The old serializer is restored temporarily in the local process from the unchanged historical engine; no historical source or result is modified. Every v2 before/after native hash matches exactly.

These clocks include engine construction, simulation and native reporting, with block records enabled for v4. They exclude validation, persistence and subsequent object cleanup from all three columns. GC is disabled within the timed generation and collected outside it. Each engine uses its own native 30,000-block stopping contract: v4 can settle a pending race after the threshold; v2 retains its unresolved endpoint.

| Matched condition | Count | Petty-v4 CPU s / condition | V2 before CPU s | V2 after CPU s | Remaining v2/v4 |
|---|---:|---:|---:|---:|---:|
| H | 19 | .11251 | .38975 | .39126 | 3.478× |
| S0 | 19 | .14008 | .52727 | .52774 | 3.767× |
| Petty SC | 19 | .14226 | .59420 | .59198 | 4.161× |
| Combined | 57 | .13162 | .50374 | .50366 | 3.827× |

The strongest architectural control, honest H at lambda=0, is .11049 → .38433 → .38485 CPU seconds, a remaining **3.483×** slowdown. For petty SC the remaining ratios at lambda 0/.005/.02 are **4.182× / 4.147× / 4.152×**. The serializer change has essentially no effect on these petty cases; their terminal paths do not exhibit the selfish outlier's shared-prefix expansion.

V2 maintains arbitrary persistent forks, general ancestry/height indexes, complete public/private frontiers, publication and reorganization history, generic target/selfish-actor reaction machinery, RNG audit state and a richer terminal scientific witness. Petty-v4 has a restricted race/state machine and simpler disposition accounting; even v2 H/S0 traverses the common general engine. The fresh profile identifies indexing, publication/reaction plumbing, repeated miner construction and dataclass/report conversion as ordinary costs. Retained deep-reorganization history creates an additional extreme cost for some non-petty conditions.

Positive-lambda and selfish-strategy comparisons deliberately differ in network/RNG/race/stopping semantics. They are matched parameter/horizon cost comparisons, **not trajectory-equivalence claims between v4 and v2**. The v2 before/after serializer comparison, and the Python/native v2 comparison, do require exact equivalence.

5. **Minimal prototype, validation and timing.**

The backend is `persistent-h-s0-petty-native-prototype-v1`. A single CPython-extension call owns compact C++ block vectors, integer actor/parent references, height/frontier structures, target-private state, natural windows, petty races, publication/reaction logs, reorganization records and rewards. There are no per-event Python calls. Reporting and direct compact extraction operate on native structures. Bulk SHA-256 uses Python's existing OpenSSL-backed hash function through a handful of C-API calls per condition; float formatting uses Python repr for the small scalar boundary, preserving canonical JSON exactly.

Python initializes the existing three `CommonRandom` streams and passes the exact 624 MT words plus position. C++ implements the same state transition, tempering and 53-bit `random()` conversion, rather than reseeding `std::mt19937`. Python-computed miner weights preserve residual arithmetic. The build prohibits fast-math and floating-point contraction. Final RNG draw counts, last draws and hashes of the exact Python state representation are preserved.

The emitted compact summary is **unattested** until unchanged Python lightweight checks, sampled selection, any required independent replay and compact consistency checks pass. The benchmark uses actual HMAC/SQLite writes to isolated stores. Its manifest filename/layout and producer identity are explicitly experimental; it cannot be loaded as a production study. Unsupported active rules fail without fallback.

The test matrix covers exact 10,000-draw RNG sequences for five seeds and three streams, twist-boundary continuations, every per-discovery trace, all output fields, direct compact extraction, and unchanged independent replay. It spans m=2/3/4, H/S0/HF/SC/member leave-outs, gamma 0/intermediate/1, lambda 0/.005/.02/1, two seeds and repetitions. Scripted tests exercise private-prefix releases and abandonment, delayed visibility, explicit-owner preference, target-present/absent multiway petty races, residual behavior, terminal leads and resource-limit status. Baselines remain common across all six rule labels. ASCII JSON escaping, including embedded NUL, is also checked.

The timing corpus contains **70 distinct H/S0/petty configurations × actual repetitions 0/1/2 = 210 conditions per backend**, all at 30,000 blocks. It is the H/S0/petty subset of the profile's real core conditions, with 19 populations and all three cardinalities/lambdas. No anchor or validation selection is adjusted. Each paired condition runs Python once and native once, alternating order. Timings include Python conversion, unchanged validation, extraction, persistence and explicit cleanup. Exact native hashes and scientific compact/attestation equality are required after every pair; independent diagnostic hash checks and result-file output are excluded from throughput clocks.

All 210 conditions naturally selected lightweight validation only in the initial trial. Replay was not disabled or replaced with a nominal percentage. Short fixture tests separately exercise full independent replay. No replay-inclusive whole-sweep native speedup is claimed from this relatively simple subset.

The first prototype measured **188.544 Python CPU seconds versus 93.932 native-path CPU seconds = 2.007×**. Native stepping took only 3.979 timed wall seconds in total, but native report/emission took 48.566 seconds and Python decoding took 10.494 CPU seconds. The remaining unchanged lightweight checks took 28.730 CPU seconds. This exposed an avoidable prototype implementation cost: constructing sorted maps for every block and publication record. A small follow-up emits these fixed schemas directly in canonical key order and reserves array buffers. No transition or validation code changed.

The final direct-emission prototype completed all **210/210 exact pairs**. Its scientific identities, raw hashes and validation attestations also match the initial prototype trial exactly.

| Whole-condition measure | Python reference | Native prototype |
|---|---:|---:|
| Total CPU seconds | 189.060 | 68.045 |
| Total timed wall seconds | 189.326 | 68.246 |
| Mean CPU seconds / condition | .9003 | .3240 |
| CPU speedup | 1× | **2.778×** |

The three actual repetition strata independently give 2.761×, 2.796× and 2.779×. These are paired workload strata, not repeated concurrency trials or confidence intervals.

| Condition type | Pairs | Python CPU seconds | Native CPU seconds | Whole-condition speedup |
|---|---:|---:|---:|---:|
| H | 57 | 37.189 | 10.562 | 3.521× |
| HF, petty | 12 | 8.204 | 2.152 | 3.811× |
| S0 | 57 | 55.503 | 21.582 | 2.572× |
| SC, petty | 57 | 60.429 | 23.194 | 2.605× |
| Petty member leave-outs | 27 | 27.735 | 10.553 | 2.628× |

By cardinality 2/3/4, speedups are 2.761×/2.907×/2.677×. By lambda 0/.005/.02, they are 2.816×/2.734×/2.755×. All **210/210 final-trial attestations are lightweight**, exactly as selected by the unchanged actual-plan policy.

The measured Python generation plus extraction is **141.643 CPU seconds**. The corresponding native kernel **including Python input preparation and raw/compact decoding** costs **37.178 CPU seconds**, a **3.810×** improvement for those operations. Whole-condition performance is lower because other work remains.

The final native path spends 4.058 timed wall seconds in state/event processing and **22.514 wall seconds in native terminal/report/emission**, plus **10.410 CPU seconds in Python decoding**, **28.919 CPU seconds in unchanged lightweight checks**, 1.767 CPU seconds in cleanup and .130 CPU seconds in persistence. The two internal native phases are wall-clock measurements; the enclosing native call and complete-condition numbers are independently measured process CPU clocks. They are not falsely presented as CPU substage timers.

The raw witness averages **13.69 MB per condition**, with 2.876 GB emitted over the 210 conditions; compact summaries total only 1.264 MB. Even this simple subset still pays heavily to emit, decode and check a rich native witness. The prototype eliminates Python engine objects and event-loop allocations, but preserves expanded witness materialization at the boundary. A finite/native representation and independently checked streaming extraction remain valuable directions; this experiment does not authorize dropping any witness or validation check.

**Decision:** a condition-level C++ implementation has demonstrated value, including ≥3× for honest H/HF and 2.778× overall. A ≥3× overall improvement remains plausible: substantial report/emission and checking costs remain computationally movable. It has **not been demonstrated for this complete mixed subset or the full six-variant study**. Do not multiply the 2.778× result across unsupported selfish/counter-fork/ignore workloads, especially the censored tail. No full four-rule backend was started; the next performance question is exact witness representation and independent verification cost, supported by this concrete prototype rather than an event-loop-only ceiling.

6. **Files, tests and reproducibility.**

New analysis code in this continuation:

- `analysis/profile_persistent_v2_boundary.py`: post-fix stage CPU timers, independent cProfile repeats, complete/censored reporting.
- `analysis/compare_persistent_v2_petty_cost.py`: bounded 57-condition three-way historical comparison.
- `analysis/native/persistent_v2_prototype.cpp`: opt-in condition kernel and direct native extraction.
- `analysis/build_persistent_v2_native_prototype.py`: local C++17 CPython-extension build.
- `analysis/persistent_v2_native_prototype.py`: exact state/identity boundary and source/binary provenance.
- `analysis/benchmark_persistent_v2_native_prototype.py`: bounded paired native/reference timing and exact output checks.
- `tests/test_persistent_v2_native_prototype.py` and `tests/test_persistent_v2_boundary_profile.py`: equivalence and instrumentation-failure tests.

This report and the JSON evidence files record the measurements. The earlier `persistent_v2_kernel_profile.md` now points here to supersede its narrow port deferral. The previous v2-only serializer correction and its tests remain in the working tree; **this continuation changes no production simulation, validation, model, scientific configuration, ID, seed, CRN or sharding implementation**. Prototype source/binary hashes are recorded separately, and the old scientific source/result files remain untouched.

Validation completed:

- `.venv/bin/python -m pytest -q tests/test_persistent_v2_native_prototype.py tests/test_persistent_v2_boundary_profile.py`: **293 passed in 9.69 seconds** after the native escaping fix.
- `.venv/bin/python -m pytest -q`: **1,597 passed, 9 xfailed in 132.16 seconds** on the final source.
- `git diff --check`: passed; new untracked source/report files were also checked for trailing whitespace and missing final newlines.
- Evidence checks confirm 210 unique native condition IDs, unchanged core-plan/validation-context digests and measured native-source/wrapper fingerprints matching the final implementation.

The first full test run caught loss of the suffix after an embedded NUL in a synthetic ASCII actor ID at the C-API string conversion boundary. Conversion now uses the explicit UTF-8 byte length. The new regression test, complete equivalence matrix and final full suite pass. Neither this issue nor its fix changes the actual core corpus's ordinary actor IDs. The final direct-emission timings were collected after that correction.

Build requirements are a C++17 compiler and the headers for the checkout's Python interpreter; no pybind11, downloaded library, package installation or production configuration change is involved. The prototype build is explicit, and the local test fixture builds it for equivalence testing:

```bash
.venv/bin/python -m analysis.build_persistent_v2_native_prototype
.venv/bin/python -m pytest -q tests/test_persistent_v2_native_prototype.py tests/test_persistent_v2_boundary_profile.py
```

The bounded commands used for the additional measurements, from this checkout and its already generated actual-plan corpus, were:

```bash
.venv/bin/python -m analysis.profile_persistent_v2_boundary --source-corpus results/persistent_v2_kernel_profile_after/corpus.json --output results/persistent_v2_boundary_postfix --total-seconds 900
.venv/bin/python -m analysis.compare_persistent_v2_petty_cost --source-corpus results/persistent_v2_kernel_profile_after/corpus.json --output results/persistent_v2_boundary_postfix/matched_petty.json
.venv/bin/python -m analysis.benchmark_persistent_v2_native_prototype --run --source-corpus results/persistent_v2_kernel_profile_after/corpus.json --output results/persistent_v2_native_prototype_direct_emission --repetitions 3 --total-seconds 900
```

Outputs refuse reuse of an existing destination. The source corpus requires its sibling `core_plan` with matching local runtime provenance; these commands are not a remote study-resume procedure. The old profiling entry point can enumerate a fresh source corpus in an isolated local destination. No benchmark here connects to a host or launches a production worker.

Evidence: [post-fix profile](persistent_v2_condition_profile.json), [matched petty comparison](persistent_v2_matched_petty_cost.json), [initial prototype](persistent_v2_native_prototype_initial.json), and [direct-emission prototype](persistent_v2_native_prototype_evidence.json). Per-condition identities, native hashes, actual validation selections, clocks and runtime/source/build fingerprints are retained.
