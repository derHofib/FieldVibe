"""Verbraucherschutz im Kundenportal (B2C): Schalter, Widerrufsbelehrung,
Muster-Widerrufsformular, Widerrufsfrist.

ACHTUNG: Alle Rechtstexte in diesem Modul sind Platzhalter und von einer
Rechtsberatung zu pruefen, bevor ein Betrieb sie gegenueber Verbrauchern
einsetzt. Die Texte dienen nur dazu, den technischen Ablauf (Anzeige,
Nachweis, Mail) durchgaengig testbar zu machen."""
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.zeit import in_lokal, tagesende_utc
from app.models.kunde import Kunde
from app.models.mandant import Mandant

MODUS_AUS = "aus"
MODUS_NUR_PRIVATKUNDEN = "nur_privatkunden"
VERBRAUCHERSCHUTZ_MODI = (MODUS_AUS, MODUS_NUR_PRIVATKUNDEN)

# Kunde.typ-Werte, die als Verbraucher (§ 13 BGB) gelten. Nur "privat": ob ein
# Privatkunde im Einzelfall gewerblich handelt, oder eine Hausverwaltung/WEG
# als Verbraucher zaehlt, ist rechtlich zu klaeren und hier nicht entscheidbar.
# typ NULL (nicht gepflegt) zaehlt vorsichtshalber NICHT als Verbraucher.
VERBRAUCHER_KUNDE_TYPEN = ("privat",)

# Fristlaenge nach § 355 Abs. 2 BGB; Beginn hier vereinfacht = Zeitpunkt der
# Annahme im Portal. Die tatsaechliche Fristberechnung (Beginn erst mit
# ordnungsgemaesser Belehrung und Vertragsschluss bzw. Leistungserbringung,
# Erloeschen nach § 356 Abs. 4/5 BGB bei vollstaendiger Leistung, Wertersatz
# nach § 357a) ist rechtlich zu klaeren und bildet dieser Wert nicht ab.
WIDERRUFSFRIST_TAGE = 14

BELEHRUNG_PLATZHALTER_VERSION = "platzhalter-v1"

_PLATZHALTER_HINWEIS = "PLATZHALTER - von Rechtsberatung prüfen. Kein rechtsgeprüfter Text."


def muster_widerrufsbelehrung(mandant: Mandant) -> str:
    fd = mandant.firmendaten or {}
    adresse = fd.get("adresse") if isinstance(fd.get("adresse"), dict) else {}
    anschrift = ", ".join(
        t for t in (adresse.get("strasse"), " ".join(filter(None, (adresse.get("plz"), adresse.get("ort"))))) if t
    )
    kontakt = ", ".join(t for t in (mandant.name, anschrift, fd.get("telefon"), fd.get("email")) if t)
    return (
        f"{_PLATZHALTER_HINWEIS}\n\n"
        "Widerrufsrecht\n"
        "Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen. "
        "Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsschlusses.\n\n"
        "Um Ihr Widerrufsrecht auszuüben, müssen Sie uns "
        f"({kontakt}) mittels einer eindeutigen Erklärung (z. B. über den Widerrufsbutton im Kundenportal, "
        "per Brief oder E-Mail) über Ihren Entschluss, diesen Vertrag zu widerrufen, informieren. "
        "Zur Wahrung der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über die Ausübung des "
        "Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.\n\n"
        "Folgen des Widerrufs\n"
        "Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von Ihnen erhalten haben, "
        "unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die Mitteilung "
        "über Ihren Widerruf dieses Vertrags bei uns eingegangen ist.\n\n"
        "Haben Sie verlangt, dass die Dienstleistungen während der Widerrufsfrist beginnen sollen, so haben Sie "
        "uns einen angemessenen Betrag zu zahlen, der dem Anteil der bis zu dem Zeitpunkt, zu dem Sie uns von der "
        "Ausübung des Widerrufsrechts hinsichtlich dieses Vertrags unterrichten, bereits erbrachten Dienstleistungen "
        "im Vergleich zum Gesamtumfang der im Vertrag vorgesehenen Dienstleistungen entspricht."
    )


def muster_widerrufsformular(mandant: Mandant) -> str:
    fd = mandant.firmendaten or {}
    adresse = fd.get("adresse") if isinstance(fd.get("adresse"), dict) else {}
    empfaenger = "\n".join(
        t
        for t in (
            mandant.name,
            adresse.get("strasse"),
            " ".join(filter(None, (adresse.get("plz"), adresse.get("ort")))),
            fd.get("email"),
        )
        if t
    )
    return (
        f"{_PLATZHALTER_HINWEIS}\n\n"
        "Muster-Widerrufsformular\n"
        "(Wenn Sie den Vertrag widerrufen wollen, dann füllen Sie bitte dieses Formular aus und senden Sie es "
        "zurück.)\n\n"
        f"An:\n{empfaenger}\n\n"
        "Hiermit widerrufe(n) ich/wir (*) den von mir/uns (*) abgeschlossenen Vertrag über die Erbringung der "
        "folgenden Dienstleistung (*):\n\n"
        "Angebot Nr.: ______________________\n"
        "Beauftragt am (*): ______________________\n"
        "Name des/der Verbraucher(s): ______________________\n"
        "Anschrift des/der Verbraucher(s): ______________________\n\n"
        "Unterschrift des/der Verbraucher(s) (nur bei Mitteilung auf Papier): ______________________\n"
        "Datum: ______________________\n\n"
        "(*) Unzutreffendes streichen."
    )


@dataclass(frozen=True)
class Belehrung:
    version: str
    text: str
    ist_platzhalter: bool


def modus(mandant: Mandant) -> str:
    """Bestandsmandanten haben den Schluessel nie gesetzt und behalten "aus"
    -- sonst aendert sich fuer sie mit dem Update unangekuendigt der Ablauf.
    Neue Mandanten bekommen "nur_privatkunden" beim Anlegen (mandanten.py)."""
    wert = (mandant.firmendaten or {}).get("portal_verbraucherschutz")
    return wert if wert in VERBRAUCHERSCHUTZ_MODI else MODUS_AUS


def ist_verbraucher(kunde: Kunde | None) -> bool:
    return kunde is not None and kunde.typ in VERBRAUCHER_KUNDE_TYPEN


def b2c_ablauf_aktiv(mandant: Mandant, kunde: Kunde | None) -> bool:
    return modus(mandant) == MODUS_NUR_PRIVATKUNDEN and ist_verbraucher(kunde)


def belehrung_fuer(mandant: Mandant) -> Belehrung:
    fd = mandant.firmendaten or {}
    text = fd.get("widerrufsbelehrung_text")
    if not isinstance(text, str) or not text.strip():
        return Belehrung(BELEHRUNG_PLATZHALTER_VERSION, muster_widerrufsbelehrung(mandant), True)
    text = text.strip()
    version = fd.get("widerrufsbelehrung_version")
    version = version.strip() if isinstance(version, str) and version.strip() else ""
    # Kurzer Textfingerabdruck in der Version: wer den Text aendert, ohne die
    # Version hochzuzaehlen, laesst sonst alte Kundenbestaetigungen auf die
    # neue Fassung zeigen.
    fingerabdruck = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return Belehrung(f"{version}#{fingerabdruck}" if version else f"ohne-version#{fingerabdruck}", text, False)


def widerrufsfrist_ende(angenommen_am: datetime) -> datetime:
    """Exklusive Obergrenze: Beginn des Tages nach dem 14. Tag. Der Tag der
    Annahme zaehlt nicht mit, die Frist endet mit Ablauf des letzten Tages
    (§§ 187 Abs. 1, 188 Abs. 1 BGB) -- in der Betriebs-Zeitzone, nicht UTC."""
    return tagesende_utc(in_lokal(angenommen_am).date() + timedelta(days=WIDERRUFSFRIST_TAGE))
