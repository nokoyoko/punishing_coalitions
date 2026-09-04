from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class Actor(str, Enum):
    TARGET = "target"
    COALITION = "coalition"
    HONEST = "honest"


class Disposition(str, Enum):
    ACCEPTED = "accepted"
    ORPHANED = "orphaned"
    UNRESOLVED = "unresolved"


class RaceOrigin(str, Enum):
    NONE = "none"
    SELFISH_RELEASE = "selfish_release"
    NATURAL_PROPAGATION = "natural_propagation"


@dataclass
class Block:
    id: int
    parent_id: int | None
    height: int
    owner: Actor
    discovery_sequence: int
    initially_withheld: bool
    publication_sequence: int | None = None
    selfish_release: bool = False
    disposition: Disposition = Disposition.UNRESOLVED

    def to_dict(self) -> dict:
        d = asdict(self)
        d["owner"] = self.owner.value
        d["disposition"] = self.disposition.value
        return d
