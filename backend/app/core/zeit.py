"""Tagesgrenzen in der Betriebs-Zeitzone.

Datums-Parameter aus dem Frontend ("YYYY-MM-DD") meinen den lokalen Kalendertag
des Betriebs, nicht den UTC-Tag -- sonst landen Eintraege kurz nach lokaler
Mitternacht (1-2 h Versatz) am Vortag. Zeitstempel bleiben in der DB UTC."""
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache
def zeitzone() -> ZoneInfo:
    return ZoneInfo(get_settings().zeitzone)


def tagesbeginn_utc(tag: date) -> datetime:
    return datetime.combine(tag, time.min, tzinfo=zeitzone()).astimezone(timezone.utc)


def tagesende_utc(tag: date) -> datetime:
    """Exklusive Obergrenze: Beginn des Folgetags. Ueber den Kalendertag statt
    +24 h gerechnet, damit Umstellungstage (23/25 h) stimmen."""
    return tagesbeginn_utc(tag + timedelta(days=1))


def in_lokal(zeitpunkt: datetime) -> datetime:
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return zeitpunkt.astimezone(zeitzone())


def montag_der_woche(tag: date) -> date:
    return tag - timedelta(days=tag.weekday())
