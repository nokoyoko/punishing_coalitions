# Model and state machine

Each event draws TARGET, COALITION, or HONEST from fixed hash shares. TARGET is
miner i, COALITION is the aggregate punishment coalition, and HONEST is the
remaining aggregate honest population. The target is never a coalition member.
A block
records ID, parent, height, owner, discovery and publication sequence,
initial-withholding status, selfish-release status, and final disposition.
Rewards are assigned only on acceptance.

## Selfish-mining states

- `lead_0`: no private attacker blocks. An attacker discovery is withheld;
  another discovery extends and is accepted on the public chain.
- `lead_1`: one withheld block. Another attacker discovery increases the lead.
  A nonattacker discovery publishes the withheld block and creates a public
  race; neither branch is resolved yet.
- `lead_2_plus`: attacker discovery increases an unbounded private deque. On a
  nonattacker discovery at lead two, the attacker publishes and wins both
  private blocks. At lead greater than two, it publishes and accepts the oldest
  private block, orphans the new competing block, and reduces its lead by one.
- `race`: the next discovery resolves the tie. The attacker always extends its
  branch. Honest hash extends it with probability gamma. Coalition hash opposes
  it after a positive oracle label and otherwise extends it with probability
  gamma using a separate draw. The winning branch's tie block and resolver are
  accepted; the losing tie block is orphaned.
- `propagation_pending`: an honestly published block is inside the one-discovery
  reduced-form propagation window. A distinct eligible honest-publishing actor
  creates a sibling; the same actor extends the pending block.

Publishing the whole branch at lead two and publishing one block at a larger
lead are both called selfish release events. The attacker never publishes a
private block merely because the run is ending.

## Miner classification and diagnostic race origin

The detector classifies the target miner once per simulation run. Its persistent
ground-truth type is `S_i=SELFISH` when `strategy=selfish` and `S_i=HONEST` when
`strategy=honest`. At initialization it samples one persistent label:

`Pr[FLAGGED | SELFISH] = TPR` and `Pr[FLAGGED | HONEST] = FPR`.

The primary workflow does not sample this detector. It forces the label and
estimates four conditional payoff vectors: `U(H,unflagged)`, `U(H,flagged)`,
`U(S,unflagged)`, and `U(S,flagged)`. TPR and FPR mix them algebraically:

`E[U|H] = (1-FPR) U(H,unflagged) + FPR U(H,flagged)`

`E[U|S] = (1-TPR) U(S,unflagged) + TPR U(S,flagged)`.

Forced runs report the imposed label and no detector-performance statistics.
Secondary sampled mode draws one label per run and reports only epochs,
flagged count, observed flag rate, and expected flag rate. Detector randomness
uses its own stream.

Separately, each public race has diagnostic origin metadata:

- `SELFISH_RELEASE`, represented by `T_r=1`; or
- `NATURAL_PROPAGATION`, represented by `T_r=0`.

Trace events outside a race use `NONE`; it carries no binary `T_r` value.

`T_r` is diagnostic only. It is not passed to the detector, does not update the
sampled-epoch report, and does not select the punishment action. At every race the
coalition consults only the target miner's already sampled persistent label.
Block release metadata and race origin remain available for auditing. The
synthetic tie helper remains only a deterministic fixture.

A punishment activation is counted when a flagged target-miner race begins while
punishment is enabled and coalition hash power is nonzero. It records the
coalition's branch commitment, whether or not the coalition happens to discover
the resolving block. Activations are reported separately by latent race origin.

## Reduced-form natural propagation

`natural_fork_rate = eta` is separate from FPR. An honestly published lead-zero
block opens a one-discovery propagation window with probability eta, drawn from
a dedicated RNG stream. The pending owner and next discoverer are compared as
three distinct represented actor classes. In honest-target experiments, every
distinct ordered pair among TARGET, COALITION, and HONEST creates a sibling on
the pending block's parent. Same-actor transitions extend the pending block.

In selfish-target experiments, only COALITION and HONEST publications can open
windows. COALITION--HONEST transitions create natural siblings. If TARGET is
the next discoverer, the explicit reduced-form rule closes the window by
accepting the pending block and has TARGET mine a private child on it; it never
creates a benign target-involved race. During a COALITION--HONEST race, a TARGET
resolver chooses a branch evenly and publishes the resolving block, then
resumes the selfish state machine. This temporary ordinary resolution is the
simplest current convention for an otherwise undefined Eyal--Sirer state.

Eta is the probability of opening a window, not an unconditional fork rate or
the probability that a fork contains TARGET.

Every block still comes from exactly one ordinary discovery draw:
the model does not inject free blocks or combine discoveries. A realized natural
race uses two discovery events to create its siblings and a third event to
resolve the race. A non-race propagation window uses two discoveries and accepts
the pending block and its child together on the second. Pending blocks receive
no reward until resolved. Outputs report both propagation windows started and
the subset that become `NATURAL_PROPAGATION` races.

Natural target-involved races occur only in honest-target experiments. Every
selfish-target race containing TARGET arises from `SELFISH_RELEASE`. Natural
COALITION--HONEST races contain no target branch, never consult the target label,
and never activate target punishment. The model does not represent forks
between two miners internal to aggregate HONEST or two miners internal to the
aggregate coalition.

## Race probabilities

For a positive label with punishment enabled, attacker-branch and competing-
branch discovery masses are respectively

`alpha_A + gamma*alpha_H` and `alpha_C + (1-gamma)*alpha_H`.

For a negative label (or no punishment), they are

`alpha_A + gamma*(alpha_H+alpha_C)` and
`(1-gamma)*(alpha_H+alpha_C)`.

This specifies aggregate randomized branch selection; no latency is simulated.
For a natural COALITION--HONEST tie, each branch owner supports its own branch;
a third-actor resolver chooses evenly. The target label is irrelevant.

## Termination and assumptions

The primary stop is target accepted blocks (a two-block resolution can overshoot
by one). If the stop occurs during a public race or propagation window, events
continue until it is resolved. Unpublished private blocks remain unresolved and receive no reward.
All published forks are therefore resolved at return unless the configured
finalization safety bound is reached. Mining is memoryless, rewards are one,
and actors outside races follow the public longest chain.
