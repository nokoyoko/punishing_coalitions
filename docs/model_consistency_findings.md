# Model consistency findings

No implementation defect requiring a Stage B rerun was found.

Under the corrected ownership rule, aggregate deterrence decreases in 896 of
1,080 adjacent-power comparisons (maximum `0.00349`) and punishment reduction
decreases in 31 (maximum `0.00120`). These are no longer safely characterized
as Monte Carlo-only noise: changing coalition power also changes competing-owner
hash and the neutral gamma mass. Values were not smoothed and require structural
interpretation.

False-positive loss at lambda zero was exactly zero in all 40,680 applicable
actor/FPR rows. Across 3,696 matched adjacent-lambda comparisons, only two
decreased, so loss generally increases with representable natural-fork
opportunities without being mechanically constrained to monotonicity; the
corrected run has one decrease among 3,696 matched adjacent-lambda comparisons.

Behaviorally identical aggregate/composition singleton populations were
deduplicated and agree by construction. Equal-hash groups require equal
candidate-population power, so residual honest power matches. Leave-one-out
changes the active set only; identity and total hash remain fixed. Cache counts
match exactly.

Inactive candidates can affect the modeled actor context despite honest
behavior: splitting honest power into explicit actors changes which distinct
actor pairs can create natural forks, because same-actor/internal-residual forks
are absent. This is a model effect, not necessarily an implementation defect.

Threshold direction with target power, gamma, and lambda is complicated by
left/right censoring and not-found rows. `threshold_audit.csv` must be used;
no monotone interpolation is warranted. The unflushed selfish private chain at
termination is a small unresolved boundary approximation and remains an open
robustness question.
