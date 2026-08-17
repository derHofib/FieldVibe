from calendar import monthrange
from datetime import date, datetime, timedelta


def add_months(d: date, months: int) -> date:
    """Calendar-month addition without pulling in python-dateutil for one
    function; clamps the day when the target month is shorter (e.g. 31.
    Januar + 1 Monat -> 28./29. Februar statt eines Overflows in den März)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def add_intervall(basis: datetime, einheit: str, wert: int) -> datetime:
    """Verallgemeinerte Variante von add_months fuer Pruefzyklen mit
    waehlbarer Einheit (siehe app.models.pruefzyklus.PRUEFZYKLUS_EINHEITEN).
    "monat" bewahrt die Uhrzeit von `basis` und wendet nur die
    Kalendermonat-Arithmetik von add_months auf das Datum an."""
    if einheit == "tag":
        return basis + timedelta(days=wert)
    if einheit == "woche":
        return basis + timedelta(weeks=wert)
    if einheit == "stunde":
        return basis + timedelta(hours=wert)
    if einheit == "monat":
        neues_datum = add_months(basis.date(), wert)
        return datetime.combine(neues_datum, basis.time(), tzinfo=basis.tzinfo)
    raise ValueError(f"Unbekannte Intervall-Einheit: {einheit}")
