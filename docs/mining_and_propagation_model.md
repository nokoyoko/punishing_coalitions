# Mining and propagation model

This appendix describes the implementation in `punishment_sim/coalition.py`,
not an intended or idealized protocol. Code references use the version audited
after Stage B.

## Configuration and actors

`Population` stores target hash power, an ordered tuple of `(candidate_id,
hash_power)`, gamma, the reduced-form natural-fork parameter, an accepted-block
target, and a base seed (`coalition.py:24-52`). It validates unique reserved-safe
identities, positive candidate shares, `0 < alpha_i < .5`, a positive residual,
and gamma/lambda in `[0,1]`. Residual power is calculated by floating-point
subtraction as `1-target-sum(candidates)`; the final draw fallback is also the
residual actor.

The target, every candidate, and `honest_residual` are persistent actor IDs.
Each independently wins discovery events and retains its own accepted blocks.
The residual is one aggregate actor, not a population of internal miners. That
aggregation means there are no forks between two residual-honest miners, just
as there are no forks internal to any other represented actor.

Candidates outside the active coalition mine honestly. Active candidates are
behaviorally identical except in a flagged target race: if one is the next
finder, it extends the non-target branch. A leave-one-out miner remains in the
candidate tuple, independently draws blocks, and retains rewards, but is removed
from the active set. No reward is transferred or shared.

## Event generation and random streams

Mining uses discrete discovery events, not timestamps or exponential clocks.
At each `step`, `_draw` samples one uniform variate and returns the first actor
whose cumulative hash share exceeds it (`coalition.py:89-98,125-126`). Hash
shares already sum to one after adding the residual; there is no renormalization.
The residual fallback absorbs a floating-point tail.

Three deterministic streams are derived by SHA-256 from
`explicit:{seed}:{discoveries|ties|natural}`: actor discovery, tie choice, and
natural-fork decisions. Repetition `r` uses `base_seed+r`. Conditional
environments with the same population and repetition therefore use common
random-number streams. Calls consume streams state-dependently, so identical
prefixes are shared but later draws need not remain aligned after paths diverge.
Separate repetitions use distinct derived seeds and are treated as independent.

Actual event order is state-dependent:

```text
draw next actor
if a race exists: choose branch, create resolving block, accept winner+resolver
else if a propagation-pending block exists: create sibling, child, or private block
else if target strategy is honest: create public block, then draw lambda decision
else if finder is selfish target: create/append withheld block
else: create public non-target block; react to current private lead
record trace after the transition
```

Thus lambda is not sampled before every discovery. It is sampled after an
honest-strategy public block, or after a non-target public block at selfish lead
zero (`coalition.py:141-172`).

## Blocks and chain state

Every block is an `EBlock` object with ID, parent, height, owner, discovery
sequence, initial-withholding flag, publication flags, and disposition
`unresolved|accepted|orphaned` (`coalition.py:55-60,99-109`). The simulator
retains a block dictionary—a partial explicit tree containing every discovered
block—plus selected state variables: accepted public `tip`, deque of selfish
private blocks, one `pending` propagation block, and one two-branch `race`.

A target block is private when created with `withheld=True`; publication flags
are set when selfish blocks are released. A public block may remain unresolved
while pending propagation. A race always contains sibling blocks owned by
distinct actors. Race resolution creates a child on the chosen branch, accepts
the chosen sibling and child, and orphans the other sibling. `_accept` increments
the stopping counter only when a block was not already accepted.

## Honest mining and branch choice

Without a race or pending state, an honest-strategy event creates a block on the
accepted tip. With probability lambda it becomes pending; otherwise it is
accepted immediately. During a target race:

* the target finder extends the target branch;
* the competing sibling owner extends its own branch;
* a flagged active member owning neither sibling extends the other branch;
* every neutral finder owning neither sibling chooses the target branch with
  probability gamma.

During a benign race with no target, a branch owner extends its own block and
all other actors choose 50/50. Gamma therefore is global, not actor-specific,
and is not used in benign non-target forks. It is used in both selfish-release
and natural-origin races if a target-owned sibling is present, but only for
neutral hash without sibling ownership or active-punisher commitment. There is one
globally visible race; the model has no miner-specific views.

## Selfish target state machine

The strategy is Eyal–Sirer-like but modified by explicit actors and the
reduced-form pending mechanism.

| Pre-state | Finder | Transition |
|---|---|---|
| lead 0 | target | create withheld block on public tip; lead 1 |
| lead 0 | non-target | create public block; accept, or mark pending with probability lambda |
| lead 1 | target | append private block; lead 2 |
| lead 1 | non-target | create public sibling; release private block and start selfish-release race |
| lead 2 | target | append private block; lead >2 |
| lead 2 | non-target | publish and accept both private blocks; orphan new honest block; lead 0 |
| lead >2 | target | append private block |
| lead >2 | non-target | publish/accept the oldest private block; orphan new honest block; reduce lead by one |
| race | target | extend target branch |
| race | competing sibling owner | extend owned non-target branch |
| race | flagged active member owning neither | extend non-target branch |
| race | neutral owner of neither | choose target with probability gamma |

At race resolution the winning sibling and resolving child earn rewards; the
losing sibling is stale. This is not a literal continuous-time or network
implementation of the standard state machine. Modifications are explicit
actor rewards, actor-based natural forks, persistent identity punishment, and
terminal handling described below. Relevant code is `coalition.py:125-172`.

When a public non-target block is pending under selfish strategy, a target
discovery accepts that public block and creates a private child; it does not
create a natural race. A different non-target actor creates a sibling race; the
same owner creates a child and both public blocks are accepted.

## Propagation, gamma, and lambda

There are no delays, topology, timestamps, partial visibility, or competing
message processes. “Propagation” means only: a public block is held in a
one-event `pending` window, and the next discovery may create a sibling.
Lambda is a Bernoulli probability per eligible public-block transition, not a
Poisson rate per unit time or per accepted block.

For an honest target, a natural pair can be any two distinct represented actor
IDs: target, each candidate, or residual. For a selfish target, pending blocks
at lead zero are created only by non-target actors; a subsequent target draw
creates a private child rather than a natural race. Hence recorded natural
pairs in selfish runs are between distinct non-target represented actors.
Same-actor pairs, residual-residual forks, and forks internal to any aggregated
actor are absent. A pending window and strategic race cannot coexist because
state branches are mutually exclusive.

Concrete selfish tie: target `t` and candidate `c1` own siblings. If target
finds next, it extends `t`; if `c1` finds next, it extends its own sibling at
both gamma endpoints. A flagged active member owning neither sibling extends
the non-target sibling. An inactive candidate, leave-one-out miner, or residual
actor owning neither extends `t` with probability gamma. An unflagged active
candidate owning neither also follows gamma. All actors observe the same siblings.

## Classification and petty punishment

`flagged` is attached to the target identity for an entire conditional run,
not inferred from blocks. `study` forces four environments per repetition:
honest/unflagged, selfish/unflagged, honest/flagged/C, and selfish/flagged/C,
plus selfish/flagged leave-one-out environments (`coalition.py:227-256`). TPR
and FPR mix these cached conditional payoffs algebraically. They are absent from
the behavioral `mining_cache_key` (`coalition.py:218-224`). TPR, FPR, reporting
epsilon, priors, and presentation labels are not its arguments. Race-origin
metadata is diagnostic only; punishment tests target ownership and the
persistent flag.

Petty punishment changes only the resolving branch choice at a target-involving
tie. It does not alter hash rate, withholding, publication, chain length, or
rewards. A neutral active finder mines a resolving block on the non-target sibling,
thereby making that branch win. When neither sibling is target-owned, branch
owners show loyalty and other finders use 50/50. The two-target-branch case is
unrepresentable because `_begin_race` asserts distinct owners. A falsely
flagged honest target can be punished only after lambda creates a natural tie;
therefore its false-positive loss is exactly zero at lambda zero.

## Rewards, stopping, and payoffs

Only accepted main-chain blocks earn one unit. Orphans and unresolved blocks
earn zero; there are no fees, uncles, partial rewards, difficulty adjustment,
or transfers. Each actor payoff in a repetition is its accepted count divided
by the total accepted count. `normalized_revenue` further divides that share by
actor hash power (`coalition.py:177-192`). All payoff comparisons use the raw
revenue share, calculated within each repetition before aggregation.

The main loop stops once `accepted_count >= target_accepted_blocks`. It then
resolves an active race or pending window, which can overshoot the target by up
to the blocks accepted in that resolution. It does **not** publish or flush a
remaining selfish private deque. Those blocks remain unresolved and earn zero.
This creates an order roughly private-lead/30,000 boundary effect, normally
small, with a plausible downward direction for selfish-target revenue. It is
paired but not necessarily canceled because conditional paths differ.
Corrected Stage B outputs retain terminal private lead, uncredited private
blocks, accepted denominator, omitted-share bound, and point/interval overlap
diagnostics; the blocks remain uncredited.

`U_i^H`, `U_i^{S,empty}`, `U_i^{S,C}`, and `U_i^{H,F,C}` are target revenue
shares in the four forced environments. Member payoffs use the same actor ID in
each environment. Baselines and leave-one-out comparisons use matched
repetitions and common seeds.

## Worked implementation traces

1. **Honest, no fork.** State lead 0, tip `p`; candidate `c1` is drawn. It
   creates public child `b(p,c1)`. Lambda draw fails, so `b` is accepted, becomes
   tip, and `c1` gains one accepted reward.
2. **Private lead.** State lead 0; selfish target is drawn. It creates withheld
   `t1` on the public tip, appends it to `private`, accepts nothing, and enters
   lead 1. Other actors still have the accepted public tip.
3. **Selfish release.** At lead 1, residual is drawn and creates public sibling
   `h1`. Target `t1` is marked published/selfish-release and the simulator stores
   race `(t1,h1)`. Neither sibling is yet accepted.
4. **Petty resolution.** Continue trace 3 with target flagged and a neutral
   active `c1`. If `c1` is drawn, it chooses `h1`, creates child `c2` on it, accepts `h1,c2`,
   orphans `t1`, clears the race, and rewards residual plus `c1`.
5. **False positive.** Honest target creates pending `t1`; a distinct candidate
   next creates sibling `c1`, producing a natural target race. If a flagged
   active member resolves next, it extends `c1`; `t1` becomes stale despite the
   target being honest. With lambda zero the pending state cannot arise.
6. **Leave one out.** Population contains `c1,c2`; active set is only `{c2}` for
   the `c1` deviation environment. `c1` remains an independent draw and reward
   recipient. In a flagged target race, a `c1` draw follows gamma, while a `c2`
   draw deterministically extends the non-target branch.

These traces use the single global race view implemented by `step`; they do not
imply miner-specific message visibility.

Corrected ownership traces: an explicit competing owner extends its block at
both gamma 0 and gamma 1; every residual-oceanic draw uses Bernoulli gamma,
including when the competing sibling bears the aggregate residual label; a neutral active punisher
chooses the non-target branch; and a leave-one-out miner owning neither uses gamma.
