from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SimulationConfig:
    target_hash_power: float = 0.25
    coalition_hash: float = 0.10
    gamma: float = 0.5
    tpr: float = 0.9
    fpr: float = 0.01
    natural_fork_rate: float = 0.0
    target_accepted_blocks: int = 10000
    seed: int = 1
    strategy: str = "selfish"
    punishment_enabled: bool = True
    forced_label: bool | None = None
    trace_path: str | None = None
    output_path: str | None = None
    include_block_records: bool = False
    max_finalization_events: int = 100000

    def __post_init__(self) -> None:
        if not 0 < self.target_hash_power < 0.5:
            raise ValueError("target_hash_power must be in (0, 0.5)")
        if not 0 <= self.coalition_hash < 1 - self.target_hash_power:
            raise ValueError("coalition_hash must be in [0, 1-target_hash_power)")
        for name in ("gamma", "tpr", "fpr", "natural_fork_rate"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.target_accepted_blocks <= 0:
            raise ValueError("target_accepted_blocks must be positive")
        if self.strategy not in {"honest", "selfish"}:
            raise ValueError("strategy must be honest or selfish")

    @property
    def honest_hash(self) -> float:
        return 1.0 - self.target_hash_power - self.coalition_hash

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"honest_hash": self.honest_hash}

    @classmethod
    def from_file(cls, path: str | Path) -> "SimulationConfig":
        data = json.loads(Path(path).read_text())
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in allowed})
