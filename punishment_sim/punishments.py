from typing import Protocol


class PunishmentRule(Protocol):
    def coalition_supports_target(self, flagged: bool, default_draw: float, gamma: float) -> bool: ...


class PettyPunishment:
    """Oppose a flagged target branch; otherwise use gamma."""
    def coalition_supports_target(self, flagged: bool, default_draw: float, gamma: float) -> bool:
        return False if flagged else default_draw < gamma


class NoPunishment:
    def coalition_supports_target(self, flagged: bool, default_draw: float, gamma: float) -> bool:
        return default_draw < gamma
