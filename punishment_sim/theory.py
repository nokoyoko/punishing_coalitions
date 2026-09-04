from decimal import Decimal


def selfish_revenue(alpha: float, gamma: float) -> float:
    """Eyal--Sirer apparent hashrate, Eq. (8), for alpha < 1/2."""
    numerator = alpha * (1-alpha)**2 * (4*alpha + gamma*(1-2*alpha)) - alpha**3
    denominator = 1 - alpha * (1 + (2-alpha)*alpha)
    return numerator / denominator


def eyal_sirer_profitability_threshold(gamma: float) -> float:
    """Vanilla Eyal--Sirer threshold (1-gamma)/(3-2*gamma)."""
    g=Decimal(str(gamma))
    if not Decimal(0) <= g <= Decimal(1):
        raise ValueError("gamma must be in [0,1]")
    return float((Decimal(1)-g)/(Decimal(3)-Decimal(2)*g))


def vanilla_selfish_mining_profitable(alpha: float, gamma: float) -> bool:
    """Strict analytic admission rule; equality is break-even, not profitable."""
    a=Decimal(str(alpha)); g=Decimal(str(gamma))
    if not Decimal(0) < a < Decimal("0.5"):
        return False
    threshold=(Decimal(1)-g)/(Decimal(3)-Decimal(2)*g)
    return a > threshold
