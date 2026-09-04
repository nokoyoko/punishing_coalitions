# Stage B methodology

Stage B uses three logically separate stages.

1. **Analytical admission.** A target/gamma pair is admitted exactly when the
   vanilla Eyal--Sirer condition `alpha > (1-gamma)/(3-2gamma)` holds, with
   `alpha < 1/2`. Equality is break-even and is not admitted. Candidate power,
   coalition composition, and natural-fork rate do not affect admission.
2. **Punishment effectiveness.** Each analytically admitted pair is simulated
   under every configured natural-fork rate and coalition configuration.
3. **Coalition credibility and stability.** Existing individual participation,
   leave-one-out, weak/strict credibility, and joint-feasibility calculations
   are applied to the simulated punishment outcomes.

Natural forks and honest-population partitioning are simulation robustness
parameters for stages 2 and 3. Simulated `U_S0-U_H` variation across candidate
power is retained as honest-population representation sensitivity; it is not a
profitability-admission rule.
