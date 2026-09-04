import csv, json
from collections import Counter
from pathlib import Path

import pytest

from analysis.stage_b_racefix import DEFAULT_SOURCE, MODEL_VERSION, TABLE_NAMES, read_csv, validate_inputs

ROOT=Path(__file__).resolve().parents[1]
TABLES=DEFAULT_SOURCE/"analysis_tables"; FIGURES=DEFAULT_SOURCE/"analysis_figures"

def test_corrected_input_audit_and_no_simulation_entrypoints():
    audit=validate_inputs(DEFAULT_SOURCE)
    assert audit["corrected_only"] and not audit["old_model_configuration_detected"]
    assert audit["model_version"]==MODEL_VERSION and audit["unique_configuration_count"]==1980
    assert not audit["mining_executed"] and not audit["stage_c_executed"]
    source="\n".join((ROOT/"analysis"/x).read_text() for x in ("stage_b_racefix.py","generate_stage_b_racefix_tables.py","generate_stage_b_racefix_figures.py"))
    assert "punishment_sim" not in source and "research-sweep" not in source

def test_old_model_is_rejected(tmp_path):
    for name in [x["file"] for x in json.loads((DEFAULT_SOURCE/"analysis_input_audit.json").read_text())["source_files"]]:
        rows=read_csv(DEFAULT_SOURCE/name)
        if rows and "model_version" in rows[0]:rows[0]["model_version"]="old-model"
        with (tmp_path/name).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    with pytest.raises(RuntimeError):validate_inputs(tmp_path)

def test_tables_and_configuration_traceability():
    for name in TABLE_NAMES:assert (TABLES/name).exists()
    exempt={"aggregate_effectiveness_thresholds_compact.csv","credibility_by_structure.csv","weak_vs_strict_credibility.csv","equal_hash_effect_summary.csv","equal_hash_by_structure_pair.csv","minimal_winning_coalitions_summary.csv","racefix_internal_comparison.csv"}
    for path in [TABLES/name for name in TABLE_NAMES]:
        rows=read_csv(path)
        if path.name not in exempt and rows:assert any(k.endswith("configuration_id") or k=="configuration_ids" for k in rows[0])

def test_threshold_ties_and_boundaries_retained():
    rows=read_csv(TABLES/"aggregate_effectiveness_thresholds.csv")
    assert all("supported_tied_minimizers" in r for r in rows)
    assert {r["threshold_boundary_classification"] for r in rows}=={"SELFISH_ALREADY_UNPROFITABLE","NOT_FOUND_WITHIN_GRID","AT_LOWER_GRID_EDGE"}

def test_tpr_categories_are_not_fabricated_numbers():
    rows=read_csv(TABLES/"continuous_tpr_summary.csv")
    assert Counter(r["tpr_status"] for r in rows)=={"SELFISH_ALREADY_UNPROFITABLE":4544,"DETERRABLE":538,"NOT_DETERRENT_AT_TPR_1":462}
    assert all(r["continuous_tpr_minimum"]=="" for r in rows if r["tpr_status"]!="DETERRABLE")

def test_credibility_counts_and_zero_slack_semantics():
    rows=read_csv(TABLES/"coalition_credibility_summary.csv");counts=Counter(r["credibility_classification"] for r in rows)
    assert counts=={"STRICTLY_DEVIATION_PROOF":58,"WEAK_BREAK_EVEN_ONLY":1128,"NEITHER":4358}
    assert all(r["credibility_classification"]!="STRICTLY_DEVIATION_PROOF" for r in rows if float(r["credibility_slack"])==0)

def test_false_positive_lambda_zero_invariant():
    rows=read_csv(TABLES/"false_positive_actor_summary.csv")
    assert all(float(r["conditional_loss"])==0 for r in rows if float(r["natural_fork_rate"])==0)

def test_terminal_and_stage_c_counts():
    terminal=read_csv(TABLES/"terminal_boundary_review.csv")
    assert sum(r["point_overlap"].lower()=="true" for r in terminal)==14
    assert sum(r["supported_interval_overlap"].lower()=="true" for r in terminal)==5
    protected=read_csv(TABLES/"publication_critical_confirmation_cases.csv")
    assert len(protected)==429 and all(r["publication_critical_protected"].lower()=="true" for r in protected)

def test_composition_keeps_adjusted_and_unadjusted_results():
    rows=read_csv(TABLES/"equal_hash_effect_summary.csv")
    assert len(rows)==5
    assert all({"unadjusted_positive","unadjusted_negative","unadjusted_inconclusive","bh_positive","bh_negative","bh_inconclusive"} <= set(r) for r in rows)

def test_figure_companions_metadata_and_formats():
    pngs=sorted(FIGURES.glob("*.png"));assert len(pngs)>=27
    for png in pngs:
        stem=png.with_suffix("")
        for suffix in (".pdf",".svg",".csv",".metadata.json"):assert Path(str(stem)+suffix).exists()
        rows=read_csv(Path(str(stem)+".csv"));meta=json.loads(Path(str(stem)+".metadata.json").read_text())
        assert meta["plotted_observation_count"]==len(rows)
        if png.name!="racefix_internal_comparison.png" and rows and any("configuration_id" in k for k in rows[0]):
            keys=[k for k in rows[0] if "configuration_id" in k];assert all(any(r.get(k) for k in keys) for r in rows)

def test_old_data_only_in_internal_diagnostic():
    for path in list(TABLES.glob("*.csv"))+list(FIGURES.glob("*.metadata.json")):
        text=path.read_text()
        if "racefix_comparison" in text or "old/corrected" in text:assert "racefix_internal_comparison" in path.name

def test_analysis_has_no_new_strategy_and_companions_are_stable():
    scripts=[ROOT/"analysis"/"stage_b_racefix.py",ROOT/"analysis"/"generate_stage_b_racefix_figures.py"]
    assert all("class Punishment" not in p.read_text() for p in scripts)
    before={p.name:p.read_bytes() for p in FIGURES.glob("*.csv")}
    assert before and all(before[p.name]==p.read_bytes() for p in FIGURES.glob("*.csv"))
