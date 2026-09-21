"""Versioned v2 trace fixtures and the immutable historical audit subjects."""
import hashlib
import json
from pathlib import Path

import pytest

from punishment_sim.coalition import Population
from punishment_sim.persistent_checkpoint import digest
from punishment_sim.persistent_v2 import NETWORK_VERSION, PersistentSimulation, Rule
from punishment_sim.persistent_v2_checkpoint import validate_run

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = json.loads((ROOT / "tests/fixtures/persistent_network_v2_golden.json").read_text())


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: f"{c['case']}-{c['strategy']}-{c['lambda']}")
def test_v2_complete_native_trace_and_identity_fixture(case):
    assert GOLDEN["network_version"] == NETWORK_VERSION
    p = Population(.2, (("c1", .1), ("c2", .1)), .5, case["lambda"], case["horizon"], case["seed"])
    flagged = case["case"] != "baseline"
    label = case["case"] if flagged else "counter_fork"
    rule = Rule(label, 1 if label == "counter_fork" else None)
    active = ("c1", "c2") if flagged else ()
    result = PersistentSimulation(p, case["strategy"], flagged, active, rule, trace_mode=True).run()
    assert result["status"] == "COMPLETE"
    assert digest(result) == case["result_sha256"]
    assert result["condition_id"] == case["condition_id"]
    validate_run(result, p, rule, 0, case["strategy"], flagged, active)


def test_historical_v1_sources_match_the_pre_correction_audit():
    audit = json.loads((ROOT / "docs/persistent_baseline_audit_evidence.json").read_text())
    for filename, expected in audit["engine_sha256"].items():
        assert hashlib.sha256((ROOT / filename).read_bytes()).hexdigest() == expected, filename
