from datetime import date


def berechne_prioritaet(
    *,
    heute: date,
    faelligkeit_am: date,
    toleranz_frueh_tage: int | None,
    toleranz_spaet_tage: int | None,
) -> int:
    """Prioritaets-Rampe fuer Dauerauftrag-Vorgaenge (Skala 1-5), passend zur
    jeweils konfigurierten Toleranz -- keine festen Tages-Schwellen, sondern
    proportional zu toleranz_frueh_tage/toleranz_spaet_tage:

    - Anlage-Tag (faelligkeit_am - toleranz_frueh_tage): Prio 1
    - Faelligkeitstag: Prio 3
    - Ende der Kulanz (faelligkeit_am + toleranz_spaet_tage): Prio 4
    - Danach (ueberfaellig, Kulanz ausgeschoepft): Prio 5

    NULL/0 bei einer Toleranz bedeutet "kein Vorlauf-/Kulanz-Fenster
    definiert" -- dann entfaellt die jeweilige Rampe (siehe unten), nicht
    weil 0 Tage Vorlauf ein Rechenfehler waeren, sondern weil sich ohne
    Fenster nichts linear verteilen laesst.

    Aufrunden statt kaufmaennisch runden (math.floor(x + 0.5) statt
    round()): bei einem Dringlichkeits-Signal ist ein zu frueh gezeigtes
    "wird knapp" harmloser als ein zu spaetes."""
    differenz_tage = (faelligkeit_am - heute).days

    if differenz_tage > 0:
        if not toleranz_frueh_tage:
            return 3
        anteil = max(0.0, min(1.0, (toleranz_frueh_tage - differenz_tage) / toleranz_frueh_tage))
        return _round_half_up(1 + 2 * anteil)

    tage_ueberzogen = -differenz_tage
    if tage_ueberzogen == 0:
        return 3
    if not toleranz_spaet_tage or tage_ueberzogen > toleranz_spaet_tage:
        return 5
    anteil = tage_ueberzogen / toleranz_spaet_tage
    return _round_half_up(3 + anteil)


def _round_half_up(wert: float) -> int:
    return int(wert + 0.5)
