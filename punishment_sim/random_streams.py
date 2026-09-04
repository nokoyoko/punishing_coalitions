import hashlib
import random


def stream(master_seed: int, name: str) -> random.Random:
    raw = hashlib.sha256(f"punishment-sim:{master_seed}:{name}".encode()).digest()
    return random.Random(int.from_bytes(raw[:8], "big"))

