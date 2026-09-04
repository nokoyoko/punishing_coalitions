# Research impact of race-owner precedence correction

Model `race-owner-precedence-v2` was rerun over the complete Stage B grid in a
new directory. All 1,980 population checkpoints and 451,440 unique simulations
are new; no pre-fix checkpoint was reused. Old outputs remain the descriptive
comparison baseline.

Old-versus-corrected differences are matched by population/coalition/member
configuration but are **not** assigned paired version-comparison confidence
intervals. Removing unnecessary owner tie draws changes state-dependent stream
alignment. Each version's own paired intervals remain valid for its internal
conditional comparisons.

## Qualitative changes

Across 5,544 coalitions, 1,990 deterrence statuses changed and 2,587 continuous
TPR edge/classification statuses changed. Punishment-reduction estimates changed
but none crossed the broad supported/refuted/inconclusive classification used
in the comparison. Baseline weak/strict member statuses changed 2,072/2,378
times; deviation weak/strict statuses changed 4,086/4,930 times. There were
1,815 changed threshold rows, including 216 effectiveness thresholds. False-
positive status changed in 11,595 FPR-expanded rows, representing 2,319 unique
configuration/coalition/actor conditions. BH-adjusted equal-hash conclusions
changed in 7,603 rows: 357 deterrence, 2,070 punishment reduction, 1,464
baseline credibility, and 1,856 each for deviation margin and slack.

Corrected effectiveness counts are 5,044 supported, 445 refuted, and 55
inconclusive. Corrected TPR classes are 4,544 selfish-already-unprofitable, 538
deterrable, and 462 not deterrent at TPR 1.

Corrected deviation credibility is substantially less robust: 151 member
margins are strictly supported, 1,742 weak break-even, 2,410 inconclusive, and
156 refuted. At coalition level 58 are strict deviation-proof, 1,128 weak-only,
and 4,358 neither.

Composition effects are now material in more families. After within-metric BH,
deterrence has 217 positive and 140 negative comparisons; punishment reduction
1,047/1,023; baseline credibility 897/975; deviation/slack 236/286. These are
exploratory multiple-comparison results and not claims of economic importance.

False-positive loss remains exactly zero at lambda zero. Threshold audit labels
918 selfish-already-unprofitable, 862 lower-edge, 825 not-found, and 545
interior rows.

## Terminal boundary diagnostic

The convention remains unchanged: terminal private blocks are uncredited.
Across 5,544 coalition conditions, maximum terminal private lead is 8; mean of
condition-level mean leads is 0.0863; mean nonzero-ending fraction is 0.0296;
and maximum omitted-share bound is 0.0002667. The diagnostic labels 5,101
negligible, 14 overlapping the point deterrence margin, and 429 requiring
review; five supported deterrence intervals have lower margins within the
conservative maximum bound. No terminal block was credited.

The corrected uncapped Stage C audit contains 5,388 reasoned candidates. The
optional ranking protects 429 publication-critical cases from a numerical cap;
Stage C was not executed.
