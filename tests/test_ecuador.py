import pytest

from smartguard.vision.ecuador import canonical, format_plate, is_valid_cedula, parse_plate


@pytest.mark.parametrize(
    ("raw", "text", "kind", "formatted"),
    [
        ("PBZ5579", "PBZ5579", "auto", "PBZ-5579"),
        ("pcx-7679", "PCX7679", "auto", "PCX-7679"),
        ("GSA123", "GSA123", "auto", "GSA-123"),
        ("IB123C", "IB123C", "moto", "IB-123C"),
        ("P8Z5579", "PBZ5579", "auto", "PBZ-5579"),  # 8 en zona de letras
        ("PBZ55T9", "PBZ5579", "auto", "PBZ-5579"),  # T en zona de dígitos
        ("PC0-7679", "PCO7679", "auto", "PCO-7679"),
        ("PBZ_5579_", "PBZ5579", "auto", "PBZ-5579"),  # relleno del OCR
    ],
)
def test_parse_valid_plates(raw, text, kind, formatted):
    plate = parse_plate(raw)
    assert plate is not None
    assert (plate.text, plate.kind, plate.formatted) == (text, kind, formatted)


@pytest.mark.parametrize("raw", ["", "XBC20", "K8C", "DBC1234", "FBC1234", "PBZ55791", "1234567", "_4_4"])
def test_rejects_non_ecuadorian_reads(raw):
    assert parse_plate(raw) is None


def test_too_many_corrections_rejected():
    assert parse_plate("P8Z55T9", max_corrections=1) is None
    assert parse_plate("P8Z55T9", max_corrections=2) is not None


def test_province_and_service():
    assert parse_plate("PBZ5579").province == "Pichincha"
    assert parse_plate("PBZ5579").service == "Particular"
    assert parse_plate("GAA1234").service == "Comercial"
    assert parse_plate("PEA1234").service == "Gubernamental"
    assert parse_plate("IB123C").service == "Motocicleta"


def test_format_and_canonical_any_plate():
    assert canonical(" pbz-5579 ") == "PBZ5579"
    assert format_plate("PBZ5579") == "PBZ-5579"
    assert format_plate("cd-1234") == "CD1234"  # no ecuatoriana: se muestra tal cual


@pytest.mark.parametrize(("number", "valid"), [
    ("1710034065", True),
    ("0926687856", True),
    ("1710034066", False),
    ("2510034065", False),  # provincia 25 no existe
    ("17100340", False),
    ("abcdefghij", False),
])
def test_cedula(number, valid):
    assert is_valid_cedula(number) is valid
