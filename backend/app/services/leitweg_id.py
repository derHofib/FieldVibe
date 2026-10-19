"""Leitweg-ID (Routing-Kennung oeffentlicher Auftraggeber, BT-10 der XRechnung).

Aufbau nach der Leitweg-ID-Spezifikation der KoSIT:
Grobadressierung (2-12 Ziffern) [- Feinadressierung (1-30 alphanumerisch)] - Pruefziffer (2 Ziffern).
Die Pruefziffer wird nach ISO 7064 (MOD 97-10, wie bei der IBAN) ueber Grob- und
Feinadressierung ohne Trennstriche berechnet: Zeichen in Zahlen wandeln, "00" anhaengen,
Pruefziffer = 98 - (Zahl mod 97).

Abgesichert ist die Rechnung durch die Beispiel-IDs 991-12345-73 und
04011000-1234512345-06 (beide ohne Buchstaben). Die Umwandlung von Buchstaben der
Feinadressierung (A=10 ... Z=35, wie bei der IBAN) folgt der ISO-7064-Konvention; die
Spezifikation war beim Schreiben nicht abrufbar, ein Beispiel mit Buchstaben liegt nicht
vor. Ein Buchstaben-Fall, der hier faelschlich abgelehnt wird, ist daher nicht
auszuschliessen -- die Formatpruefung allein bleibt in jedem Fall gueltig."""
import re

_FORMAT = re.compile(r"(\d{2,12})(?:-([A-Z0-9]{1,30}))?-(\d{2})")


def pruefziffer(grob_und_fein: str) -> str:
    zahl = int("".join(str(int(zeichen, 36)) for zeichen in grob_und_fein) + "00")
    return f"{98 - zahl % 97:02d}"


def normalisiere_und_pruefe(wert: str | None) -> str | None:
    """Gibt die ID in Grossschreibung ohne Leerraum zurueck; leer/None -> None.
    Wirft ValueError mit verstaendlicher Meldung bei falschem Format oder Pruefziffer."""
    if wert is None:
        return None
    ist = "".join(wert.split()).upper()
    if not ist:
        return None
    treffer = _FORMAT.fullmatch(ist)
    if treffer is None:
        raise ValueError(
            "Leitweg-ID hat ein ungültiges Format. Erwartet: Grobadressierung (2-12 Ziffern), "
            "optional -Feinadressierung (bis 30 Buchstaben/Ziffern) und -Prüfziffer (2 Ziffern), "
            "z. B. 04011000-1234512345-06"
        )
    grob, fein, ziffern = treffer.groups()
    if pruefziffer(grob + (fein or "")) != ziffern:
        raise ValueError("Die Prüfziffer der Leitweg-ID stimmt nicht – bitte Tippfehler prüfen")
    return ist
