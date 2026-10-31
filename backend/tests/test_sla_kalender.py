from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.services.sla_kalender import (
    KalenderLeerFehler,
    SlaKalender,
    add_geschaeftsminuten,
    fortschritt_prozent,
    geschaeftsminuten_zwischen,
)

BERLIN = ZoneInfo("Europe/Berlin")
TAG = ((time(7, 0), time(17, 0)),)
MO_FR = SlaKalender(fenster={d: TAG for d in range(5)}, bundesland="BY")


def dt(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=BERLIN)


def test_freitag_abend_laeuft_am_montag_weiter():
    assert add_geschaeftsminuten(dt(2026, 10, 30, 16, 30), 60, MO_FR) == dt(2026, 11, 2, 7, 30)


def test_start_am_sonntag_beginnt_montag_frueh():
    assert add_geschaeftsminuten(dt(2026, 11, 1, 12), 30, MO_FR) == dt(2026, 11, 2, 7, 30)


def test_innerhalb_des_fensters():
    assert add_geschaeftsminuten(dt(2026, 11, 2, 9), 120, MO_FR) == dt(2026, 11, 2, 11)


def test_feiertag_wird_uebersprungen():
    # 3.10.2026 ist Samstag; 1.5.2026 (Freitag) ist Feiertag.
    assert add_geschaeftsminuten(dt(2026, 4, 30, 16, 0), 120, MO_FR) == dt(2026, 5, 4, 8, 0)


def test_feiertage_nicht_ausnehmen():
    kal = SlaKalender(fenster=MO_FR.fenster, feiertage_ausnehmen=False)
    assert add_geschaeftsminuten(dt(2026, 4, 30, 16, 0), 120, kal) == dt(2026, 5, 1, 8, 0)


def test_rund_um_die_uhr():
    kal = SlaKalender(rund_um_die_uhr=True)
    assert add_geschaeftsminuten(dt(2026, 11, 1, 23, 0), 120, kal) == dt(2026, 11, 2, 1, 0)


def test_mehrtaegig():
    # 3 Arbeitstage = 1800 min, Start Mo 07:00 -> Mi 17:00
    assert add_geschaeftsminuten(dt(2026, 11, 2, 7), 1800, MO_FR) == dt(2026, 11, 4, 17)


def test_sommerzeitwechsel_fenster_hat_echte_stunden():
    # 29.3.2026 (Sonntag, Umstellung 02:00 -> 03:00): Fenster 00:00-06:00 = 5 echte Stunden.
    kal = SlaKalender(fenster={6: ((time(0), time(6)),)}, feiertage_ausnehmen=False)
    assert geschaeftsminuten_zwischen(dt(2026, 3, 29, 0), dt(2026, 3, 29, 6), kal) == 300
    assert add_geschaeftsminuten(dt(2026, 3, 29, 0), 300, kal) == dt(2026, 3, 29, 6)


def test_minuten_zwischen_ueber_wochenende():
    assert geschaeftsminuten_zwischen(dt(2026, 10, 30, 16), dt(2026, 11, 2, 8), MO_FR) == 120


def test_minuten_zwischen_rueckwaerts_ist_null():
    assert geschaeftsminuten_zwischen(dt(2026, 11, 2, 9), dt(2026, 11, 2, 8), MO_FR) == 0


def test_fortschritt():
    start = dt(2026, 11, 2, 8)
    faellig = add_geschaeftsminuten(start, 240, MO_FR)
    assert fortschritt_prozent(start, faellig, dt(2026, 11, 2, 11), MO_FR) == 75
    assert fortschritt_prozent(start, faellig, dt(2026, 11, 2, 13), MO_FR) == 125


def test_leerer_kalender_bricht_ab():
    with pytest.raises(KalenderLeerFehler):
        add_geschaeftsminuten(dt(2026, 11, 2, 8), 10, SlaKalender())
