"""Grenzwert-Markierung von Zahlenfeldern (validation.warn_min/warn_max, Konzept formulare Abschnitt 5).

Reine Logik ohne I/O, geteilt von PDF-Renderer und MCP-Ansicht. Nur Anzeige: gespeichert wird immer."""
from decimal import Decimal
from typing import Any, Literal

Richtung = Literal["ueber", "unter"]


def _fmt_grenze(grenze: Any) -> str:
    zahl = Decimal(str(grenze))
    return str(int(zahl)) if zahl == zahl.to_integral_value() else str(zahl.normalize()).replace(".", ",")


def grenzwert_abweichung(feld_typ: str, validation: dict[str, Any] | None, wert: Any) -> tuple[Richtung, str] | None:
    """(Richtung, Grenze als Text), wenn der Wert ausserhalb liegt. Ein nicht lesbarer Wert
    (Freitext im Zahlenfeld) bleibt unmarkiert."""
    if feld_typ != "zahl" or wert is None or wert == "" or isinstance(wert, bool):
        return None
    validation = validation or {}
    try:
        zahl = Decimal(str(wert).strip().replace(",", "."))
        warn_max = validation.get("warn_max")
        warn_min = validation.get("warn_min")
        if warn_max is not None and zahl > Decimal(str(warn_max)):
            return "ueber", _fmt_grenze(warn_max)
        if warn_min is not None and zahl < Decimal(str(warn_min)):
            return "unter", _fmt_grenze(warn_min)
    except ArithmeticError:
        return None
    return None


def grenzwert_text(abweichung: tuple[Richtung, str] | None) -> str | None:
    if abweichung is None:
        return None
    richtung, grenze = abweichung
    return f"{'über' if richtung == 'ueber' else 'unter'} {grenze}"
