from calendar import monthrange
from datetime import date


def add_months(d: date, months: int) -> date:
    """Calendar-month addition without pulling in python-dateutil for one
    function; clamps the day when the target month is shorter (e.g. 31.
    Januar + 1 Monat -> 28./29. Februar statt eines Overflows in den März)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)
