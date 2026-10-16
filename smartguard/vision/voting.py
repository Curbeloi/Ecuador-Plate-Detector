"""Confirmación por votación entre frames (placas leídas, armas detectadas).

Una sola detección no basta: algo se confirma cuando la misma clave (texto de la placa, tipo de
arma) se ve ``votes_required`` veces dentro de ``window_s`` segundos. Luego no se vuelve a confirmar
durante ``cooldown_s`` para que un mismo hecho frente a la cámara genere un solo evento.

Con ``merge_near_duplicates`` (placas) tampoco se confirman claves que difieren en un solo carácter
de una recién confirmada (``PON7651`` tras ``PDN7651``): casi siempre son la misma placa mal leída.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable


def _differs_at_most_one(a: str, b: str) -> bool:
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) <= 1


class Voter:
    def __init__(
        self,
        votes_required: int = 3,
        window_s: float = 4.0,
        cooldown_s: float = 60.0,
        merge_near_duplicates: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.votes_required = votes_required
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.merge_near_duplicates = merge_near_duplicates
        self._clock = clock
        self._reads: dict[str, deque[float]] = defaultdict(deque)
        self._confirmed_at: dict[str, float] = {}

    def add(self, text: str) -> bool:
        """Registra una detección; devuelve ``True`` solo en la que confirma la clave."""
        now = self._clock()
        if self._near_recent(text, now):
            return False
        if len(self._reads) > 256:
            self._forget_stale(now)
        reads = self._reads[text]
        reads.append(now)
        while reads and now - reads[0] > self.window_s:
            reads.popleft()
        if len(reads) < self.votes_required:
            return False
        self._confirmed_at[text] = now
        del self._reads[text]
        return True

    def _near_recent(self, text: str, now: float) -> bool:
        if not self.merge_near_duplicates:
            return now - self._confirmed_at.get(text, -float("inf")) < self.cooldown_s
        return any(
            now - at < self.cooldown_s and _differs_at_most_one(text, confirmed)
            for confirmed, at in self._confirmed_at.items()
        )

    def _forget_stale(self, now: float) -> None:
        """Descarta lecturas sueltas (errores del OCR) que ya salieron de la ventana."""
        for text in [t for t, reads in self._reads.items() if now - reads[-1] > self.window_s]:
            del self._reads[text]
        for text in [t for t, at in self._confirmed_at.items() if now - at >= self.cooldown_s]:
            del self._confirmed_at[text]

    def recently_confirmed(self, text: str) -> bool:
        return self._clock() - self._confirmed_at.get(text, -float("inf")) < self.cooldown_s
