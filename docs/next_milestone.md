# Next milestone: effectiveness and individual credibility

Replace aggregate COALITION with three to five explicit coalition-candidate
miners, each with an ID, hash share, branch policy, block ownership, and reward
account. Retain one aggregate residual-honest actor initially. Configuration
selects any subset C as punishers; nonmembers mine honestly and use default tie
breaking.

For each target/network configuration and repetition, reuse common discovery
variates across: honest-target benchmark, unpunished selfish target, punishment
by C, and each unilateral deviation C minus j. Branch-choice and detector
streams remain separate. Report paired payoff differences with Student-t
confidence intervals across independent repetitions.

Compute effectiveness from target payoff under P_C versus its all-honest
benchmark, plus reduction from unpunished selfish mining. Compute baseline
credibility for each j from P_C versus no punishment. Compute deviation-proof
credibility from P_C versus P_(C minus j). Never infer individual credibility
from aggregate coalition revenue.

Start with target i, three coalition candidates, and one aggregate residual
honest actor. Enumerate all eight subsets exactly. For larger candidate sets,
begin with singleton, full, leave-one-out, and hash-power-threshold subsets;
avoid exhaustive exponential enumeration until screening identifies relevant
regions. Shapley values, Banzhaf indices, transferable utility, and core
analysis remain out of scope.
