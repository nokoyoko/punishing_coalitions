# Punishment simulator

This repository contains an independent, event-driven Python simulator for one
honest-or-selfish target miner, an aggregate punishment coalition, and remaining
honest hash power. The target is never part of the coalition. The first
milestone studies identity-based noisy detection and petty tie-breaking only.

## Install and quick start

Python 3.10+ is supported (3.12 is the intended research environment).

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[test]'
python3 -m punishment_sim run --config configs/example.json
python3 -m punishment_sim compare --config configs/example.json --output results/compare.json
python3 -m punishment_sim sweep --config configs/petty_sweep.json --output results/sweep.csv --aggregate results/aggregate.csv
python3 -m punishment_sim smoke-test
python3 -m punishment_sim coalition-study --config configs/coalition_dev.json --summary-output results/coalition_dev/summary.csv --member-output results/coalition_dev/members.csv --repetition-output results/coalition_dev/repetitions.csv --detector-output results/coalition_dev/detector.csv
python3 -m punishment_sim coalition-sweep --config configs/coalition_sweep_dev.json --output-dir results/coalition_sweep_dev --dry-run
python3 -m punishment_sim transition-report --zero-json results/transition_zero/summary.json --natural-json results/transition_natural/summary.json --output-dir results/transition_report
```

Use `configs/smoke_sweep.json` for a near-instant end-to-end sweep check;
`petty_sweep.json` is the somewhat larger demonstration grid.

Configuration is JSON. A run specifies `target_hash_power`, `coalition_hash`,
`gamma`, `tpr`, `fpr`, `natural_fork_rate`, `target_accepted_blocks`, `seed`,
`strategy` (`honest` or `selfish`), `punishment_enabled`, optional
`forced_label`, and optional output/trace paths. The honest
share is derived and validated. `coalition_hash` is deliberately excluded from
the ordinary honest gamma mass. The coalition's default tie policy uses the
same gamma, but an independent random stream.
For configuration compatibility, `target_hash_power` denotes the target miner's hash
share even when `strategy` is `honest`.

Run JSON includes complete parameters, totals, classification mode/label, and
per-actor discovery/disposition/revenue data, race counts by latent origin, and
punishment activations by origin. Compare JSON contains honest/unflagged,
honest/flagged, selfish/unflagged, and selfish/flagged conditional payoff
vectors plus algebraically mixed expected payoffs.
Sweep CSV has one row per grid point and independent repetition; aggregate CSV
reports mean, standard error, and normal-approximation 95% intervals. Set
`include_block_records` to true for an auditable (potentially large) block array
in run JSON; records always remain available in memory to engine users.
Compare and sweep outputs also report coalition revenue, the cost of punishment
in selfish-type runs, and target-miner/coalition false-positive costs in
honest-type runs.
Primary comparisons force one persistent target-miner label per run. TPR/FPR are
then applied algebraically, so sweeping them does not rerun mining simulations.
Single-run sampled mode remains available when `forced_label` is omitted and
reports only a compact sampled-epoch summary. Race origins are diagnostic
metadata only and never serve as detector inputs.

```bash
python3 -m pytest -q
python3 -m punishment_sim validate --config configs/validation.json --output results/validation.csv
python3 -m punishment_sim smoke-test --output results/smoke_report.json --trace-output results/smoke_traces.jsonl
```

## Current limitations

There is no detailed network latency distribution, difficulty, fees,
attribution error, delayed detection, or punishment beyond tie-breaking. The
`natural_fork_rate` process is a reduced-form one-event propagation window, not
a peer-to-peer network simulation. It models forks between distinct represented
actor classes, but not within the aggregate coalition or HONEST population. The
simulator stops primarily at accepted-chain length and resolves a race already
in progress, but never gifts unpublished private blocks to the chain. See
[docs/model.md](docs/model.md) for exact semantics and
[docs/validation.md](docs/validation.md) for validation scope.

The explicit-member, non-transferable-utility study is documented in
[docs/coalition_study.md](docs/coalition_study.md).

In target-involving ties, persistent explicit sibling owners remain on their
own branches. `gamma` applies to neutral explicit hash and always splits the
aggregate residual-oceanic mass, even when its aggregate label appears on the
competing sibling. Active neutral punishers choose the non-target branch.
Forks internal to residual oceanic mass remain unmodeled.
