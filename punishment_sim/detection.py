from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Protocol

class Detector(Protocol):
    def classify(self, truth: bool) -> bool: ...


@dataclass
class NoisyOracle:
    tpr: float
    fpr: float
    rng: random.Random
    epochs: int = 0
    flagged_count: int = 0

    def record(self, truth: bool, observed: bool) -> bool:
        self.epochs += 1
        self.flagged_count += int(observed)
        return observed

    def classify(self, truth: bool) -> bool:
        observed = self.rng.random() < (self.tpr if truth else self.fpr)
        return self.record(truth, observed)

    def report(self, truth: bool) -> dict:
        expected = self.tpr if truth else self.fpr
        return {"epochs": self.epochs, "flagged_count": self.flagged_count,
                "observed_flag_rate": self.flagged_count / self.epochs if self.epochs else None,
                "expected_flag_rate": expected}
