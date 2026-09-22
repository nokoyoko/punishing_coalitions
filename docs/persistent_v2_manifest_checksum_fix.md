# Persistent-v2 study-manifest canonicalization fix

This report records the earlier fix and its tests. The fix remains in place.
The subsequent [validation policy](persistent_v2_validation_policy.md) also
changes the compact/shard control contract and source-evidence audit; use its
separate-checkout deployment instructions for that update.

The fresh-plan startup failure was reproduced locally without mining. A synthetic
36-population, 28-shard plan failed immediate `load_manifest` with `study manifest
checksum`. A temporary plan using the actual core configuration now passes the
same round trip for all 126,666 populations; its scope and native plan hash match
the existing core scope artifact exactly.

## Root cause and fix

`canonical_json` uses `json.dumps(..., sort_keys=True)`. On the first pass, Python
integer dictionary keys are sorted numerically, then emitted as JSON strings.
After loading, those string keys sort lexicographically. For example, integer
keys 2 and 10 become keys `"2"` and `"10"`, reversing their canonical order.
Consequently the original unsigned object and its JSON round trip can have
different digests. Single-digit keys alone do not expose the problem, explaining
why small existing tests could pass even when configured for 28 shards.

Immediately before computing `study_id`, `prepare_study` now performs:

```python
unsigned = json.loads(canonical_json(unsigned))
manifest = {**unsigned, "study_id": digest(unsigned)}
```

This normalizes the **entire unsigned manifest**, including nested dictionaries
and JSON array representations, using the same canonical serializer as durable
`atomic_json`. The returned manifest and its reloaded representation now agree.
Neither the shared serializer/digest nor `load_manifest` validation changed.
No dictionary-specific loader casts, fallback checksums, or broken-manifest
migration were introduced.

`receipt_key_sha256` remains outside `study_id`; per-shard random receipt keys
still get their own provenance checks when the shard store opens. Manifest
checksums, source/Python provenance, SQLite integrity, plan hashes, and HMAC
receipts all remain enforced.

## Scientific and historical compatibility

Unchanged: scientific configuration/task IDs, population IDs, condition IDs,
repetition seeds, population-to-shard ownership, network/model versions, scientific
parameters, mining semantics, baseline sharing and statistical reductions.
A pre-fix native-plan fixture pins population/task/condition identities, all six
rules, owners, and seeds at repetitions 0/4/5/9. The new code reproduces it exactly.

The manifest's `study_id` and the source-code runtime fingerprint change. New
receipt keys and receipt namespaces are created by replanning, as usual. Existing
strict source validation is retained; this fix does not authorize historical
checkpoint import or make old producer fingerprints interchangeable. Historical
petty-v4 files and persistent historical model semantics were not changed.

The .51 timing benchmark remains unmodified historical evidence. Its source audit
now removes only the documented three-line normalization addition and requires
the resulting shard-module hash and **every other** runtime component to match
the original benchmark. This is an evidence check, not an exception in checkpoint
loading. No benchmark was rerun.

## Regression checks

The new `tests/test_persistent_v2_manifest.py` covers:

- fresh prepare/serialize/load equality, intended design and exact scope, occupied
  single- and double-digit shard keys, and idempotent prepare;
- nested metadata beyond the two current scope dictionaries;
- checksum rejection for changes to design, scope, cardinality counts, shard
  counts, runtime metadata, or the plan digest;
- receipt-key exclusion from study ID, deterministic study ID despite fresh keys,
  and rejection of incorrect receipt-key provenance;
- modified plan content and malformed SQLite rejection;
- all 28 worker startups, stopping at the normal pre-condition hook before any
  simulation constructor can run;
- a real subprocess `plan` CLI followed by the worker CLI, with the same no-mining
  startup stop;
- unchanged pre-fix scientific identities, seeds, ownership and model versions.

All tests in that file forbid simulation construction. The complete existing suite
also ran with the user's explicit authorization for small local test fixtures.

Validation: `.venv/bin/python -m pytest -q tests/test_persistent_v2_manifest.py`
passed all **14** no-mining regressions. The full `.venv/bin/python -m pytest -q`
suite completed with **1,069 passed, 9 expected historical-v1 failures**, in
92.39 seconds. `git diff --check` and new-file whitespace checks passed. The
remote recovery block passed `bash -n` syntax validation without execution.

## Remote recovery commands — supplied, not executed

Install the corrected code in the remote checkout first. With the failed workers
already exited, run this **in Bash from that checkout's root**. The example uses
its `.venv/bin/python` for both planning and workers; use the same intended Python
environment throughout. The archive step preserves the broken directory instead
of deleting it. It does not try to repair its checksum.

```bash
set -euo pipefail
pc_python=.venv/bin/python
pc_study=results/persistent_v2_core_2to4_1pct_10rep_51pct
pc_config=configs/persistent_v2_core_2to4_1pct_10rep.json
pc_archive="${pc_study}.failed-manifest-$(date -u +%Y%m%dT%H%M%SZ)"

test -x "$pc_python"
test -d "$pc_study"
test ! -e "$pc_archive"
mv -- "$pc_study" "$pc_archive"

"$pc_python" -m punishment_sim.persistent_v2_shards plan "$pc_config" "$pc_study"
"$pc_python" - "$pc_study" "$pc_config" <<'PY'
import json
import sys
from pathlib import Path
from punishment_sim.persistent_v2_shards import load_manifest, normalize_design

manifest = load_manifest(sys.argv[1])
expected = normalize_design(json.loads(Path(sys.argv[2]).read_text()))
assert manifest['design'] == expected
assert expected['shard_count'] == 28
assert expected['repetitions'] == 10
assert expected['composition']['systematic']['member_counts'] == [2, 3, 4]
assert manifest['scope']['populations'] == 126666
print('Fresh manifest validated:', manifest['study_id'])
PY

pc_logs="$pc_study/phase-I-logs"
mkdir "$pc_logs"
for pc_shard in {0..27}; do
  nohup "$pc_python" -m punishment_sim.persistent_v2_shards run "$pc_study" \
    --shard "$pc_shard" --rep-start 1 --rep-end 5 \
    > "$pc_logs/shard-$pc_shard.log" 2>&1 < /dev/null &
  printf '%s\t%s\n' "$pc_shard" "$!" >> "$pc_logs/workers.tsv"
done
printf 'Phase I launched; logs and PIDs: %s\n' "$pc_logs"
```

`set -e` prevents worker launch if fresh planning or validation fails. Inspect the
per-shard logs for execution status; background submission alone is not completion.
Do not start Phase II until all Phase-I workers finish and whole-study preliminary
coverage passes the existing merge/export checks. No automatic Phase-II launch is
included.

These recovery/launch commands were **not executed**. No production simulation,
SSH, `/xtra` access, remote job, or historical-data modification occurred during
this fix. Only local plan enumeration and authorized test fixtures ran.
