# Paper output plan

`paper_output_validation.csv` maps fourteen proposed figures/tables to exact
files, columns, filters, aggregation, uncertainty, multiplicity, and Stage C
needs. All can be constructed from existing Stage B mining outputs and derived
tables without rerunning mining.

Use `threshold_audit.csv` for threshold panels, never the unqualified raw edge
flag. Use refined credibility tables for weak/strict claims. Use continuous TPR
bootstrap intervals and paired false-positive intervals directly. Equal-hash
figures should display raw paired effect sizes and intervals, with BH-adjusted
status as a secondary exploratory annotation. Minimal winning coalitions remain
based on the validated weak rule; a strict version should be filtered from the
refined coalition table before publication.

Stage B is paper-output complete, but boundary thresholds, selected TPR
transitions, weak/strict credibility disagreements, and representative
composition contrasts are marked for Stage C confirmation. No polished figure
was generated in this validation pass.
