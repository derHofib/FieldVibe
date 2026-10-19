import re

_MUSTER = re.compile(r"\d{5,9}")


def personenkonto_normalisieren(wert: str | None, name: str) -> str | None:
    """Leer = Konto entfernen (der Export vergibt dann wieder eines). Nur das
    Format; Bereich und Laenge haengen von der Sachkontenlaenge des Mandanten
    ab und werden in der Route geprueft."""
    if wert is None:
        return None
    wert = wert.strip()
    if not wert:
        return None
    if not _MUSTER.fullmatch(wert) or not wert.isascii():
        raise ValueError(f"{name} muss aus 5 bis 9 Ziffern bestehen")
    return wert
