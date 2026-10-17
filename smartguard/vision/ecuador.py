"""Reglas de placas y cédulas de Ecuador.

Formatos admitidos:
- Auto: tres letras + cuatro dígitos (``PBZ-5579``) o el formato antiguo de tres dígitos (``PBZ-557``).
- Moto: dos letras + tres dígitos + una letra (``IB-123C``).

La primera letra identifica la provincia. El OCR confunde letras y dígitos parecidos (O/0, I/1,
S/5, B/8...), así que cada posición se corrige según lo que el formato espera allí.
"""

import re
from dataclasses import dataclass

PROVINCES = {
    "A": "Azuay",
    "B": "Bolívar",
    "U": "Cañar",
    "C": "Carchi",
    "X": "Cotopaxi",
    "H": "Chimborazo",
    "O": "El Oro",
    "E": "Esmeraldas",
    "W": "Galápagos",
    "G": "Guayas",
    "I": "Imbabura",
    "L": "Loja",
    "R": "Los Ríos",
    "M": "Manabí",
    "V": "Morona Santiago",
    "N": "Napo",
    "Q": "Orellana",
    "S": "Pastaza",
    "P": "Pichincha",
    "K": "Sucumbíos",
    "T": "Tungurahua",
    "Z": "Zamora Chinchipe",
    "Y": "Santa Elena",
    "J": "Santo Domingo de los Tsáchilas",
}

# Segunda letra de las placas de auto: tipo de servicio. Cualquier otra letra es particular.
SERVICES = {
    "A": "Comercial",
    "U": "Comercial",
    "Z": "Comercial",
    "E": "Gubernamental",
    "X": "Uso oficial",
    "M": "Gobierno municipal",
}

_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "7": "T", "8": "B"}
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "Z": "2", "A": "4",
             "S": "5", "G": "6", "T": "7", "B": "8"}

# (tipo, máscara) en orden de preferencia cuando dos formatos empatan. L = letra, D = dígito.
_FORMATS = (("auto", "LLLDDDD"), ("auto", "LLLDDD"), ("moto", "LLDDDL"))


@dataclass(frozen=True)
class Plate:
    text: str
    """Placa canónica, sin guion: ``PBZ5579``."""
    kind: str
    """``auto`` o ``moto``."""

    @property
    def formatted(self) -> str:
        split = 3 if self.kind == "auto" else 2
        return f"{self.text[:split]}-{self.text[split:]}"

    @property
    def province(self) -> str:
        return PROVINCES[self.text[0]]

    @property
    def service(self) -> str:
        if self.kind == "moto":
            return "Motocicleta"
        return SERVICES.get(self.text[1], "Particular")


def canonical(text: str) -> str:
    """Mayúsculas y solo letras y dígitos: ``" pbz-5579 "`` -> ``"PBZ5579"``."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def _coerce(text: str, mask: str) -> tuple[str, int] | None:
    """Ajusta ``text`` a ``mask`` corrigiendo confusiones; devuelve (texto, correcciones)."""
    chars = []
    corrections = 0
    for char, expected in zip(text, mask, strict=True):
        if expected == "L" and char.isdigit():
            char = _TO_LETTER.get(char)
            corrections += 1
        elif expected == "D" and char.isalpha():
            char = _TO_DIGIT.get(char)
            corrections += 1
        if char is None:
            return None
        chars.append(char)
    return "".join(chars), corrections


def parse_plate(raw: str, max_corrections: int = 2) -> Plate | None:
    """Interpreta una lectura del OCR como placa ecuatoriana, o ``None`` si no lo es."""
    text = canonical(raw)
    best: tuple[int, Plate] | None = None
    for kind, mask in _FORMATS:
        if len(text) != len(mask):
            continue
        coerced = _coerce(text, mask)
        if coerced is None:
            continue
        candidate, corrections = coerced
        if candidate[0] not in PROVINCES or corrections > max_corrections:
            continue
        if best is None or corrections < best[0]:
            best = (corrections, Plate(candidate, kind))
    return best[1] if best else None


def differs_by_one_char(a: str, b: str) -> bool:
    """``PON7651`` vs ``PDN7651``: típico error del OCR sobre la misma placa."""
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1


def format_plate(text: str) -> str:
    """Formato legible para cualquier placa guardada, sea o no ecuatoriana."""
    plate = parse_plate(text, max_corrections=0)
    return plate.formatted if plate else canonical(text)


def is_valid_cedula(number: str) -> bool:
    """Valida una cédula ecuatoriana (provincia, tercer dígito y dígito verificador módulo 10)."""
    if not re.fullmatch(r"\d{10}", number):
        return False
    province = int(number[:2])
    if not (1 <= province <= 24 or province == 30) or int(number[2]) >= 6:
        return False
    total = 0
    for i, digit in enumerate(number[:9]):
        product = int(digit) * (2 if i % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    return (10 - total % 10) % 10 == int(number[9])
