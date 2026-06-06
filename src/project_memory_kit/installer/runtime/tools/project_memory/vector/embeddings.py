from __future__ import annotations

import hashlib


class DeterministicEmbeddings:
    def __init__(self, size: int = 64):
        self.size = size

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = digest
        while len(values) < self.size:
            for byte in seed:
                values.append((byte / 255.0) * 2.0 - 1.0)
                if len(values) == self.size:
                    break
            seed = hashlib.sha256(seed).digest()
        return values

