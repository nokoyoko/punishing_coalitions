**Historical first phase.** The C++ deferral in this document is superseded by the [condition-kernel investigation](persistent_v2_condition_kernel.md), which expands the measured boundary, re-profiles the corrected code, and implements and measures an exact native prototype. Statements below about an unimplemented prototype describe the earlier phase only.

Persistent-v2 performance investigation — local evidence, 22 September 2026

The measured bottleneck is broader than Python event stepping. I implemented an exact v2 terminal-serialization correction, preserving the original serializer as the reference. **No C++ backend was implemented, and no C++ performance or equivalence claim is made.** The profile does not justify an event-loop-only port as the next step toward the requested ≥3× complete-condition improvement while leaving the remaining production work unchanged.

The correction cuts one real expensive selfish condition from 199.42 to 77.42 CPU seconds (2.58×). Across 227 other matched conditions, throughput is essentially unchanged. Including that outlier, the 228-condition measured total improves 1.30×. These are unweighted diagnostic results, not a production-duration estimate. Two further expensive conditions do not have complete matched timings.

The existing Kinakuta run was untouched. All executions were bounded local fixtures, tests, or profiles. No SSH, `/xtra` access, remote job, production sweep, or historical-result deletion occurred.

1. **Profiling methodology.** `analysis/profile_persistent_v2_kernel.py` enumerates the actual core plan, preserving its complete sampled-validation context and original anchors. It takes the existing quick benchmark's deterministic 18 populations: one balanced and one skewed composition in every `(m ∈ {2,3,4}, λ ∈ {0,.005,.02})` cell. It adds one real gamma-zero population, chosen by minimum SHA-256 rank with salt `kernel-gamma-zero-v1`. Selection does not depend on observed runtime.

   The 19 populations span gamma 0, .25, .5, .75, 1; target powers .10–.35; and coalition totals .11–.49. They yield exactly 230 unique conditions at native repetition index 0 (base/actual seed 51000), configured for 30,000 accepted blocks: 19 H, 19 S0, 24 HF(C), 114 SC(C), and 54 leave-one-out conditions. SC covers all six rules in every cardinality/lambda/composition cell. Every member's leave-one-out is included for all rules at one population of each cardinality. This is stratified coverage, not uniform sampling of the production population distribution.

   Event stepping is timed separately from `report()`, `_validate_fresh`, and the native HMAC-authenticated compact-store write. Validation also exposes lightweight, native-replay, extraction, and compact-validation timers. The event loop uses the existing step implementation and the original stopping/resource checks; native reports and validation use production code. The native stopping convention can slightly overshoot 30,000 after a publication batch; no extra settlement is added.

   A second exact trajectory execution supplies cProfile data for 59 selected cases: 1,770,001 accepted blocks and 2,407,182 discoveries. Those repeats matched block ledgers, reorganizations, and RNG snapshots. Instrumented measurements are kept separate from unprofiled CPU/wall costs. Function percentages below use the inclusive profile envelope; they are cProfile elapsed-time shares of a CPU-bound phase, not direct hardware counters. Inclusive rows overlap. Allocation-related calls are visible, but this is not a complete allocator census.

   The initial uncapped diagnostic was interrupted when a second extreme selfish case remained in terminal serialization for several minutes. Its completed records were preserved. The bounded reference run attempted all 230 cases: 227 complete, two trajectory timeouts, and one endpoint censored by structural expansion. The updated run reproduced the same 227 native hashes and attestations. One censored selfish case was subsequently completed under an explicit larger budget, giving 228 matched complete conditions. The initial failed reporting-only tuple/list equality assertion in a separate outlier probe was discarded as benchmark evidence; the final outlier measurement was rerun cleanly through the committed profiler.

   The remaining incomplete matched cases are:

   - Selfish SC, m=2, λ=.02, target .29, coalition (.24,.25), gamma .5: trajectory exceeded the 20-second phase budget. An earlier uncapped execution reached terminal serialization but was interrupted there. No complete cost or equivalence claim is made for it.
   - Ignore SC, m=4, λ=0, target .32, coalition (.09,.09,.10,.10), gamma .75: trajectory completed in 1.62 CPU seconds, but its 3,561,793 terminal path entries exceeded the default 1,000,000-entry report budget.

   Current tooling additionally caps measured work at 900 seconds by default (excluding plan preparation and final diagnostic-output bookkeeping). Censored states receive no completed validation attestation or compact result. The recorded reference trial preceded addition of that overall cap; its per-phase and path limits were active.

2. **Measured Python hotspots.** For the 227 fully timed reference cases, event stepping used 165.80 CPU seconds, native reports 29.40, validation/extraction 141.55, and persistence .136: 336.89 CPU seconds total. Event stepping was 49.2%, report construction 8.7%, validation/extraction 42.0%, and persistence .04%.

   Representative event-loop profile:

| Component/function | Self % | Inclusive % | Calls/accepted block | Interpretation |
|---|---:|---:|---:|---|
| Ancestry index insertion | 8.34 | 11.93 | 4.19 | Binary-lifting index construction |
| Discovery step | 7.01 | 99.26 | 1.36 | Entire discovery orchestration |
| Publication | 4.50 | 48.11 | 1.32 | Batch/frontier/policy/reaction coordination |
| Independent selfish actors | 3.78 | 13.32 | 1.32 | Snapshot reaction rounds and chain bookkeeping |
| Eligible tips | 3.67 | 13.64 | 2.33 | Rule-specific parent candidates |
| Miner construction | 2.50 | 10.50 | 1.36 | Rebuilds miner objects during actor selection |
| Actor selection | 1.17 | 12.40 | 1.36 | Includes miner reconstruction and RNG |
| Public frontier update | 2.75 | 10.03 | 1.32 | Sets, heights, and target-tip checks |
| Ownership/gamma choice | 1.36 | 6.49 | 1.26 | Explicit ownership, probabilities, tie draw |
| Ancestry query | 0.78 | 3.48 | 1.48 | Cached jump-table traversal |
| Counter-fork policy | 1.18 | 8.16 | 0.57 | Defended depth, refresh/reanchor, termination |
| Ostracism publication | 0.50 | 0.70 | 0.24 | Rejection ancestry and episode bookkeeping |
| Canonical adoption/rewards | 2.26 | 2.98 | 1.32 | Ordinary-case reorganization accounting |
| Common RNG wrapper | 0.87 | 1.22 | 2.22 | All three common streams |
| Delayed visibility | 0.42 | 0.42 | 1.08 | Visibility wrapper; other propagation costs occur inside step/publish |

`sorted`, `sum`, and list `append` contribute 4.03%, 3.79%, and 3.04% self time in this profile. Block construction, dictionaries/sets, private states, publication logs, reaction logs, and ancestry indexes remain allocated Python structures. The production engine discards `public_events`, but still constructs the temporary event dictionary and retains publication/reorganization/reaction ledgers. These are measured optimization candidates; none of that simulation behavior was changed in this patch.

The costly selfish case has a very different profile. A separate complete native 30,000-block trajectory profile, whose final native hash still matches the reference, measured:

| Function | Self % | Inclusive % | Calls/accepted block |
|---|---:|---:|---:|
| Canonical adoption and reward updates | 47.99 | 71.25 | 2.57 |
| Height lookup | 22.54 | 22.54 | 6066.23 |
| Selfish release decisions | 9.88 | 18.31 | 5.92 |

Its 77,776 discoveries leave 17,611 terminal branches, 44,034,951 explicit terminal path entries, and 29,251,518 removed-block entries over 17,414 reorganizations. The longest terminal path has 13,222 blocks. The original serializer called `asdict` on shared-prefix blocks repeatedly, overwriting the same dictionary entries. Native replay reconstructed the terminal state with that same serializer, repeating the cost.

A separate 3,000-block scaling diagnostic spent approximately two-thirds of its instrumented run in final reporting. It made 221,563 `asdict` calls and 2,437,189 `_asdict_inner` calls. This reduced-horizon probe is explicitly not a production condition identity or a substitute for the 30,000-block measurements.

The fix collects the union of frontier block IDs in a set and serializes each once, in the same final sorted order. All branch paths, canonical exposure/reward fields, private states, pending visibility, policy diagnostics, and bounds remain present and identical. Nothing is cached across snapshots or discoveries. The original historical `TreeEngine.terminal_state` remains unchanged and callable as the reference.

Top priorities indicated by the evidence are: remove repeated terminal conversion (implemented); address duplicated explicit branch/reorganization representation and its repeated validation/hashing costs with an exact contract; then consider native acceleration of reorganization traversal/reward bookkeeping and ordinary event-loop indexing/actor selection. The latter language change alone leaves substantial mandatory production work.

3. **Historical petty-v4 comparison.** Both engines received closely matched populations, horizons, target strategies, flags, and coalitions. The table gives the ratio of summed v2 mining-plus-report CPU to summed historical-v4 run CPU; validation/persistence are excluded from both sides.

| Condition | λ=0 | λ=.005 | λ=.02 |
|---|---:|---:|---:|
| H | 3.87× | 4.87× | 2.80× |
| S0 | 3.90× | 4.47× | 4.26× |
| SC | 4.41× | 4.68× | 4.60× |

Each zero-lambda cell has seven comparisons; positive-lambda cells have six. H at λ=0 is the strongest architectural control: an honest, unflagged single chain in both engines. S0/SC and positive-lambda comparisons include deliberately different network/rule/RNG contracts and richer v2 output obligations. They are not payoff-equivalence tests or evidence that the engines are scientifically interchangeable. Both implementations are Python, so these ratios do not establish a language-only penalty.

4. **C++ architecture and port decision.** No compiled backend was added. On the completed reference subset, eliminating the entire event-loop cost would cap complete-condition speedup at 1.97× if other work stayed fixed. Even eliminating both event stepping and report construction caps it at 2.38×. These are Amdahl-style ceilings for this measured subset, not predictions for Kinakuta or a redesigned validation representation. After the serializer fix, the expensive selfish condition spends only 22.52 of 77.42 CPU seconds in event stepping; eliminating that portion caps its further gain near 1.41×.

Python execution is a substantial cost, but the profile does not establish the requested ≥3× complete-condition case for an event-loop-only port under the current remaining costs. The C++ implementation, cross-language harness, and C++ benchmark stages were therefore not undertaken. This is a deliberate profile-led deferral, not a claim that those stages have been completed.

If a later port proceeds, an appropriate design would keep Python planning, identity/seeding, sharding, storage, HMAC, validation selection, and statistics, with a single compiled call operating on integer actors/blocks, contiguous parent/height/state vectors, and explicit frontiers/private chains. It must address trace/terminal representation together with an equivalently strict validator before assuming the rich ledger can be omitted. That is a design sketch, not implemented code.

5. **Files added/changed.**

- `punishment_sim/persistent_v2_terminal.py`: exact terminal serializer with deduplicated block conversion.
- `punishment_sim/persistent_v2.py`: v2-only integration; discovery/policy/RNG code unchanged.
- `punishment_sim/persistent_v2_compact.py`: includes the new serializer in runtime provenance.
- `analysis/profile_persistent_v2_kernel.py`: actual-plan corpus, separated profiling, bounded censoring, exact native-hash/attestation comparisons.
- `tests/test_persistent_v2_terminal.py`: 181 serializer/native/replay equivalence cases.
- `tests/test_persistent_v2_kernel_profile.py`: budget/structural-count checks and prevention of attesting censored runs.
- `tests/test_persistent_v2_quick_benchmark.py`: profile inventory/identity/coverage test, using the original full-plan validation context.
- `tests/test_persistent_v2_compact.py`, `tests/test_persistent_v2_51pct_evidence.py`: retain historical measurements under their historical source identity rather than falsely asserting today's source bytes are unchanged.
- `docs/persistent_v2_kernel_profile_before.json`, `docs/persistent_v2_kernel_profile_after.json`, and this report: measured evidence, exact hashes, profiles, grouped timings, and limitations.

6. **RNG/CRN audit.** No RNG implementation changed. Current v2 uses separate Python `random.Random` sources named `discoveries`, `ties`, and `natural`, seeded from the first eight bytes of SHA-256 of `NETWORK_VERSION:RNG_VERSION:actual_seed:stream_name`. Actual seed remains base seed plus repetition. The common stream excludes the punishment rule; draw count, last draw, and SHA-256 of the Python state representation remain in the native result. Exact native-hash comparisons include these RNG snapshots.

For a future exact C++ port, Python can initialize the existing generator and pass its 624-word MT state plus position into an implementation of the exact transition, tempering, and Python 53-bit `random()` conversion. Return state/count/last draw to Python for its unchanged snapshot formatting. Preserve stream consumption and pass existing Python-computed miner/residual weights without changing arithmetic order. Do not reseed `std::mt19937` or substitute another generator. No cross-language RNG implementation or test exists in this patch.

7. **Differential-test design.** The implemented differential harness concerns the serializer, not C++. It compares the new base terminal snapshot directly with the unchanged historical serializer after each of 35 discoveries, then compares complete native reports at the fixture horizon and invokes strict native replay. It spans six rules; m=2/3/4; λ=0/.005/.02; gamma 0/intermediate/1; H, S0, HF, SC and leave-one-out fixtures. The real core-plan corpus additionally includes every leave-one-out member at all three cardinalities. A deliberately shared-prefix fork verifies that serialization occurs once per emitted block and that later discoveries cannot observe a stale cache.

The unchanged existing suite exercises defended-depth exhaustion, refresh/reanchor/supersession, petty multiway/target-absent/delayed-visibility races, explicit ownership/oceanic residual behavior, ostracism roots/descendants, simultaneous/cascading/multiblock selfish releases, terminal private states, and reward accounting. This patch changes no transition implementation. This is not a substitute for the complete Python/C++ per-step harness that a future backend would require.

8. **Exact equivalence results.** 181 focused tests passed. All 227 ordinary completed core conditions and the additional expensive selfish condition have identical native result hashes and identical validation attestations before/after: 228 total, with no numerical tolerance. Complete native hashes cover discrete ledgers, actor payoffs, IDs, and RNG state. The independently profiled expensive trajectory also matches its original native hash. No equivalence result is claimed for the two remaining censored native endpoints or for C++.

9. **Existing test suite.** Final full run: `.venv/bin/python -m pytest -q` → **1,304 passed, 9 xfailed in 122.64 seconds**. The first full run exposed a historical-source-hash assertion that needed to be updated for this exact source change; the final full run passed. `git diff --check` passed. Local test fixtures were authorized; no remote tests were run.

10. **Benchmark workload.** The before/after comparison consists of the same 227 complete core-plan conditions plus the same separately completed expensive selfish condition. It uses actual 30,000-block stopping, production native recording, unchanged sampled selection including risk overrides, native lightweight/replay checks, compact extraction/validation, and authenticated persistence. No mining result cache is reused for timings. H/S0 are represented once per population and reported as shared baselines. Totals below sum timed production stages and exclude plan construction, diagnostic profile repeats, historical-engine comparisons, and report-file output. Engine construction and object teardown were not separately captured by the stage timers; consequently these are timed-stage comparisons, not whole-worker end-to-end throughput measurements. No claimed C++ success criterion rests on excluding those costs. There was one local before/after trial, with some independent local diagnostics/tests running concurrently; process CPU cost is primary. No parallel-throughput or Kinakuta-duration claim is made.

11–13. **Python timings and end-to-end speedup; C++ timings unavailable.**

| Matched workload | Conditions | Reference CPU s | Updated CPU s | Reference timed wall s | Updated timed wall s | CPU speedup |
|---|---:|---:|---:|---:|---:|---:|
| Ordinary completed subset | 227 | 336.89 | 335.63 | 337.51 | 336.64 | 1.004× |
| Including expensive selfish condition | 228 | 536.31 | 413.05 | 537.74 | 414.46 | 1.298× |

For all 228 matched conditions: mining plus native reporting is 282.64 → 220.25 CPU seconds; validation plus extraction is 253.53 → 192.66; persistence is .136 → .142. Total CPU per condition is 2.352 → 1.812 seconds. Conditions per timed wall second are .424 → .550. For the ordinary subset alone, .673 → .674 conditions/second is effectively no change.

The expensive selfish condition (`4dc4dc72b090112b003c112144c20cbbc07618f29318ca48faa7c93b49827574`) retains native hash `233b2dfab004ef76251bc947bf3f0999fd2d3a13e71bdc1bfa1cda26630fb62d`:

| Stage | Reference | Updated | Clock |
|---|---:|---:|---|
| Mining plus native report | 87.44 s | 25.75 s | CPU |
| Event stepping alone | Not separately timed in original complete run | 22.52 s | CPU |
| Native report alone | Not separately timed in original complete run | 3.23 s | CPU |
| Validation plus extraction | 111.99 s | 51.67 s | CPU |
| Lightweight checks | 8.71 s | 8.41 s | Wall |
| Native replay | 95.20 s | 35.10 s | Wall |
| Compact extraction | 8.36 s | 8.52 s | Wall |
| Complete condition including persistence | 199.42 s | 77.42 s | CPU |

The two independent before/after measurements do not justify fine-grained claims near 1.00×. The outlier gain is substantial but is below the requested 3× complete-condition criterion, and the matched aggregate is only 1.30×. The reference uses the old serializer, not a C++ comparison.

14. **Breakdowns for the Python serializer change.** These include the separately completed outlier and exclude the two unmatched conditions. They are unweighted diagnostic strata; ratios near one are measurement noise.

| Rule | Conditions | Reference CPU s | Updated CPU s | CPU speedup |
|---|---:|---:|---:|---:|
| counter_fork_k1 | 32 | 39.36 | 39.50 | 0.997× |
| counter_fork_k2 | 32 | 43.22 | 43.28 | 0.999× |
| counter_fork_k3 | 32 | 44.00 | 43.99 | 1.000× |
| ignore | 31 | 55.26 | 53.13 | 1.040× |
| petty | 32 | 34.21 | 34.70 | 0.986× |
| selfish | 31 | 286.10 | 163.47 | 1.750× |
| shared_baseline | 38 | 34.16 | 35.00 | 0.976× |

| Cardinality | Conditions | Reference CPU s | Updated CPU s | CPU speedup |
|---|---:|---:|---:|---:|
| 2 | 65 | 288.16 | 166.75 | 1.728× |
| 3 | 86 | 116.43 | 115.43 | 1.009× |
| 4 | 77 | 131.72 | 130.87 | 1.006× |

| Lambda | Conditions | Reference CPU s | Updated CPU s | CPU speedup |
|---|---:|---:|---:|---:|
| 0 | 121 | 182.38 | 181.04 | 1.007× |
| 0.005 | 54 | 277.43 | 155.12 | 1.789× |
| 0.02 | 53 | 76.50 | 76.89 | 0.995× |

The native path vectors remain large. On a 64-bit interpreter, the outlier's terminal-path and removed-block lists alone require at least approximately 559 MiB of element-pointer storage; added-block lists, block objects, dictionaries, and JSON buffers are additional. This is a structural lower bound computed from measured entry counts, not measured peak RSS. The patch eliminates repeated conversions, not the representation's memory growth.

15. **Sampled replay compatibility.** The sampled policy, full-plan anchors, risk detection, lightweight invariants, strict native replay, compact schema, checksums, and HMAC contract are unchanged. The new serializer is used when replay reconstructs the same terminal snapshot, and compares exactly with the old representation.

In the ordinary subset, 31/227 conditions received full replay (13.7%): 30 had simultaneous-selfish risk, 29 had cascading-selfish risk, and one was hash-selected. These reasons overlap. Every one of the 30 completed flagged-selfish conditions in that subset required replay; the additional expensive selfish condition also required replay. Thus the assumption that approximately 99% of these diagnostic trajectories can omit the rich native replay representation is false. The observed replay fraction is not an estimate of the whole production sweep.

Lightweight checking also walks terminal branch paths and serializes native data for finite/JSON checks. Extraction hashes the native/terminal/branch structures. The current native-hash and path-validation contracts cannot be preserved merely by dropping those vectors. An alternate strict compact/streaming representation would need its own explicit contract and equivalence evidence; it was not introduced here.

16. **Scientific invariance and provenance.** Model/network versions, punishment definitions, gamma/lambda semantics, scientific task/population/condition IDs, seeds and all RNG streams, CRN pairing, repetitions, payoff definitions, estimators, and shard ownership are unchanged. The regenerated full core-plan digest remains `94777cf6121c6f8c49d2b37d90b5f2f9681e551cc82dbc25ebc2813c91d4379e`. The before/after design, validation context, and ordered condition-ID/owner inventory were compared exactly.

Runtime source provenance changes: `persistent_v2` imports/calls the new serializer, `persistent_v2_compact` fingerprints it, and `persistent_v2_terminal` is a newly tracked source. A fresh manifest gets a new runtime producer/study ID. Strict `load_manifest` correctly rejects mixing this runtime into an old study. No bypass, historical import, in-place manifest update, or compatibility exception was added. Historical petty-v4/v1 source files and historical results remain untouched.

17. **Build/install requirements for a future local checkout on Kinakuta.** There is no C++ extension, compiler requirement, pybind11 dependency, or new model/backend version. Existing project Python requirements remain (≥3.10); local evidence was collected with CPython 3.13.3 on macOS arm64. The profiler's time limits require Unix signals (Linux/macOS). Source/Python-version provenance remains strict.

From the updated repository checkout, using its existing virtual environment:

```bash
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

These commands have not been run remotely. No C++ build or installation instructions can truthfully be supplied for an unimplemented backend.

18. **Exact bounded commands for later use.** From the updated repository checkout, this runs only the fixed diagnostic corpus with a ten-minute measured-work budget, per-phase limits, and structural censoring. Use a new output directory; the tool refuses an existing destination. Plan enumeration itself does not mine.

```bash
.venv/bin/python -m analysis.profile_persistent_v2_kernel --run --output results/persistent_v2_kernel_profile_bounded_host --total-seconds 600 --phase-seconds 20
```

Print status, completed/censored counts, and completed-stage CPU totals without executing any simulations:

```bash
.venv/bin/python -c 'import json,collections; p=json.load(open("results/persistent_v2_kernel_profile_bounded_host/profile.json")); rows=[r for r in p["cases"] if r["status"]=="COMPLETE"]; print(p["status"]); print(dict(collections.Counter(r["status"] for r in p["cases"]))); print("unexecuted",len(p.get("unexecuted_condition_ids",[]))); print({k:sum(r.get(k,{}).get("cpu_seconds",0) for r in rows) for k in ("trajectory","native_report","validation_and_extraction","persistence")})'
```

Optional **single-condition** bounded reproduction of the measured expensive case, using that freshly generated corpus and its original validation context (up to three minutes of measured work, with a larger explicit path budget):

```bash
.venv/bin/python -m analysis.profile_persistent_v2_kernel --run --output results/persistent_v2_kernel_outlier_host --source-corpus results/persistent_v2_kernel_profile_bounded_host/corpus.json --condition-id 4dc4dc72b090112b003c112144c20cbbc07618f29318ca48faa7c93b49827574 --phase-seconds 90 --total-seconds 180 --max-path-entries 50000000 --no-cprofile --compare docs/persistent_v2_kernel_profile_before.json
```

The stored reference hashes were measured with CPython 3.13.3; cross-version native equality has not been established by this investigation. Use the same Python version for an exact reference comparison. A mismatch remains fatal. A slower host can produce a censored result at the budget; that is not a successful completed-condition timing. These commands are for later isolated diagnostics, not Phase-I workers or a sweep launch. None was executed on Kinakuta.

19. **Production recommendation.** The narrowly scoped Python serializer change has exact local evidence and passing regression tests, but does not solve the overall compute-feasibility problem. Do not treat this report as a production-readiness recommendation for C++: no backend exists, no cross-language equivalence suite ran, and there are no C++ timings. The measured next design problem is the explicit branch/reorganization representation and the cost of its strict validation, particularly on risk-selected selfish trajectories. A later C++ decision should include those unavoidable costs and must still satisfy exact RNG/native-output equivalence. No production-duration extrapolation is made.

Detailed per-condition hashes, clocks, runtime fingerprints, censoring records, and profile tables are preserved in [the reference evidence](persistent_v2_kernel_profile_before.json) and [the comparison evidence](persistent_v2_kernel_profile_after.json). Larger local diagnostic artifacts, including the interrupted initial run, remain under ignored `results/` directories; they were not deleted.
