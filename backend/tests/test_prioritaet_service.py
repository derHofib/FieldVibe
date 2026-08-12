from datetime import date, timedelta

import pytest

from app.services.prioritaet_service import berechne_prioritaet


@pytest.mark.parametrize(
    "versatz_tage,erwartet",
    [(-2, 1), (-1, 2), (0, 3), (1, 4), (2, 4), (3, 5), (10, 5)],
)
def test_rampe_mit_gleicher_toleranz_frueh_und_spaet(versatz_tage, erwartet):
    faelligkeit_am = date(2026, 8, 18)
    heute = faelligkeit_am + timedelta(days=versatz_tage)
    assert (
        berechne_prioritaet(
            heute=heute,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=2,
            toleranz_spaet_tage=2,
        )
        == erwartet
    )


def test_rampe_streckt_sich_proportional_zu_hoeherer_toleranz():
    """Dieselbe relative Position (Anlage-Tag) muss bei hoeherer Toleranz
    weiterhin Prio 1 ergeben, nicht ploetzlich hoeher ausfallen."""
    faelligkeit_am = date(2026, 8, 18)
    anlage_tag = faelligkeit_am - timedelta(days=5)
    assert (
        berechne_prioritaet(
            heute=anlage_tag,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=5,
            toleranz_spaet_tage=5,
        )
        == 1
    )
    mitte = faelligkeit_am - timedelta(days=2)  # 3 von 5 Tagen Vorlauf verstrichen
    assert (
        berechne_prioritaet(
            heute=mitte,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=5,
            toleranz_spaet_tage=5,
        )
        == 2
    )


def test_ohne_vorlauf_fenster_direkt_prio_drei_am_anlage_tag():
    faelligkeit_am = date(2026, 8, 18)
    assert (
        berechne_prioritaet(
            heute=faelligkeit_am,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=None,
            toleranz_spaet_tage=None,
        )
        == 3
    )


def test_ohne_kulanz_fenster_sofort_ueberfaellig():
    faelligkeit_am = date(2026, 8, 18)
    heute = faelligkeit_am + timedelta(days=1)
    assert (
        berechne_prioritaet(
            heute=heute,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=None,
            toleranz_spaet_tage=None,
        )
        == 5
    )


def test_faelligkeitstag_selbst_ist_immer_prio_drei():
    faelligkeit_am = date(2026, 8, 18)
    assert (
        berechne_prioritaet(
            heute=faelligkeit_am,
            faelligkeit_am=faelligkeit_am,
            toleranz_frueh_tage=7,
            toleranz_spaet_tage=7,
        )
        == 3
    )
