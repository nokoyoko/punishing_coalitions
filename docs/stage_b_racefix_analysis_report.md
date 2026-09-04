# Corrected Stage B analysis report

This package analyzes only the completed `race-owner-precedence-v2` Stage B
outputs. It does not rerun mining, execute Stage C, or introduce a punishment
strategy. Branch owners remain on their own branches and gamma applies only to
neutral miners. The input audit records 1,980 deterministic population
configuration IDs and repetition-level support for plotted uncertainty.

## Effectiveness and detector thresholds

Across 5,544 coalition conditions, effectiveness is supported for 5,044,
refuted for 445, and inconclusive for 55. On the 90 aggregate singleton
environment surfaces, 63 are classified as selfish mining already
unprofitable, 12 supported thresholds occur at the lower tested grid edge, and
15 are not found in the tested grid. Edge results are censored observations,
not interpolated estimates or proof of a true minimum. Heatmaps therefore keep
these cases categorical. Target power, neutral propagation gamma, and the
natural-fork rate jointly alter the observed threshold; censoring prevents a
universal directional claim.

Continuous TPR classifications are 4,544
`SELFISH_ALREADY_UNPROFITABLE`, 538 `DETERRABLE`, and 462
`NOT_DETERRENT_AT_TPR_1`. Numeric TPR values and paired-tuple bootstrap
intervals are reported only for deterrable cases. Representative plots retain
the other two states categorically in their companion data.

## Credibility

The regenerated corrected counts exactly match the validation target: 58
coalitions are strictly deviation-proof, 1,128 are weak or break-even only,
and 4,358 are neither. Weak coalitions are not described as robust, positively
incentivized, or tolerant of positive participation costs. Member-level paired
intervals and the weakest-member evidence remain attached to configuration
IDs. The minimal-winning source yields 608 weak-credible rows across 33
environments and 50 strict-credible rows across 23 environments; ties are
retained rather than arbitrarily selected.

## Equal-active-hash composition

Each of five payoff metrics has 4,050 corrected matched comparisons.
BH-adjusted positive/negative counts are 217/140 for deterrence, 1,047/1,023
for punishment reduction, 897/975 for baseline participation gain, and
236/286 for both deviation margin and credibility slack. Median absolute
effects are respectively 1.25e-5, 9.67e-5, 5.33e-5, and 1.78e-5. Statistical
support alone is not interpreted as practical importance. These results
support neither universal composition invariance nor universal dependence.

## False positives and terminal boundary

Conditional loss is kept separate from FPR-weighted expected cost. Every
lambda-zero false-positive loss is exactly zero. The largest corrected
conditional honest-target loss is about 0.00206. The deterrence-versus-loss
plot is explicitly a tradeoff display, not welfare, utility, or optimality.

The terminal review contains all 14 conditions whose point deterrence margin
overlaps the conservative omitted-share bound and all five supported cases
plausibly affected. Maximum terminal private lead is eight blocks and the
maximum omitted-share bound is 0.0002667. These cases remain confirmation
candidates; terminal private blocks remain uncredited.

## Interpretation and confirmation status

The corrected effectiveness, TPR, credibility, composition, false-positive,
and boundary tables are ready for preliminary interpretation subject to their
recorded intervals and censoring. The reason-coded mapping retains all 5,388
Stage C candidates and all 429 protected publication-critical cases. Stage C
has not been launched. Boundary thresholds, inconclusive margins, detector
transitions, weak/strict credibility boundaries, terminal overlaps,
composition comparisons, high false-positive exposure, and visible
nonmonotonicities remain candidates for higher precision.

The sole pre-fix use is the prominently labeled internal model-correction
diagnostic. It is not a scientific comparison and carries no paired
old-versus-corrected interval because random-stream alignment changed.

Important remaining model limitations include the lack of physical network
propagation realism, no residual-honest internal forks, finite parameter-grid
censoring, and no real-world implementation-cost inference. Conclusions do
not extend beyond petty tie-breaking or to punishment strategies not simulated.

## Reproducibility

Run from the repository root:

```sh
.venv/bin/python -m analysis.generate_stage_b_racefix_tables
MPLCONFIGDIR=/private/tmp/punishing-coalitions-mpl python3 -m analysis.generate_stage_b_racefix_figures
```

Every figure has PNG, PDF, SVG, companion CSV, and metadata JSON outputs.
Scientific companions contain corrected configuration IDs. The table and
figure programs import no simulator entry point.
