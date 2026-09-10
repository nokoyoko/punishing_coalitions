# Oceanic race ownership correction v4

Current model/cache identifier: `race-owner-oceanic-all-races-v4`.

The explicit engine now grants target-absent branch ownership only to persistent
explicit actors. The residual ocean uses one 50/50 draw even when a sibling carries
its label. The basic engine applies the same residual exclusion; its aggregate
coalition policy in target-involved races is unchanged. Target-involved explicit
ownership, punishment, and gamma semantics are unchanged. Both race constructors
assert an empty private chain. Normal transitions already satisfy this invariant.

A single deferred neutral draw represents persistent first-seen assignment because
the next discovery resolves the race. There is no repeated reconsideration. Natural
fork generation still excludes same represented actor pairs, including internal
residual-residual forks; this patch does not introduce a network model.

## Validation and historical provenance

The pre-patch v3 source was saved before editing. For 36 cases, complete outputs
including every block record and event trace were compared exactly against v4:
gamma 0/0.5/1, seeds 1/17, honest/selfish strategy, active sets empty/c1/c1+c2,
flagged true, target hash .2, candidate hashes .1/.15, lambda zero, 200 accepted
blocks. All were identical. `tests/fixtures/oceanic_v3_zero_lambda.json` records
pre-patch output SHA-256 digests and the pre-patch source digest. A permanent test
checks the corrected engine against these independently captured historical outputs.

The focused v4 tests cover branch order, controlled threshold draws, gamma
isolation, inactive/leave-one-out and active actors, explicit owner priority,
residual natural-fork transitions in both engines, private-state invariants,
RNG consumption, basic coalition policy preservation, and stale version rejection.
Historical v3 output tests still assert v3 provenance, independently of the current
runtime version. Historical results are not relabeled or deleted.

## Checkpoint compatibility

* Explicit **v3, lambda=0** mining work is behaviorally compatible with this minimal
  patch: the changed selector path is unreachable, and assertions add no draws.
  This includes honest, selfish, full-coalition and leave-one-out runs. Exact
  representative comparisons support that structural argument. Reuse still
  requires matching every other population, strategy, seed, coalition, repetition,
  stopping-rule and schema field. Pre-v3 work is not covered by this conclusion.
* **lambda>0 v3** work is not generally compatible, including gamma=.5: the fix
  changes ownership, not the gamma threshold. New residual draws can also shift
  later tie choices. Treat all positive-lambda checkpoints as stale; an individual
  run avoiding the changed path would require separate complete evidence.
* Direct loading of a v3 checkpoint remains rejected. The follow-up local
  preparation adds an explicit derived compatibility envelope with source-v3
  execution provenance, source checksums and strict validation. This is not a
  version-check bypass and does not claim that old mining ran under v4.

## Prepared targeted rerun procedure (not executed)

See [the manual production runbook](oceanic_v4_targeted_rerun_plan.md) for exact
scope, tested importer rules, positive-lambda execution filtering, strict
analysis-only merge and downstream comparison commands. The source v3 files must
remain available and unchanged. The importer has only been tested on synthetic
fixtures here; actual production schema/provenance must pass its checks before use.

The sampled experiment retains analytical Eyal-Sirer admission, all 42 authorized
environments and the complete original design. No production simulations,
checkpoint import, remote merge or Stage C execution occurred during preparation.
