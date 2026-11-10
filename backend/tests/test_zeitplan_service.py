"""Reine Terminlogik des Zeitplans -- ohne Datenbank, nur In-Memory-Strukturen."""
import uuid
from datetime import date

import pytest

from app.services.zeitplan_service import (
    PlanElement,
    PlanKante,
    ZeitplanRegelverstoss,
    ZeitplanZyklus,
    aendere_element,
    aktualisiere_phasenspannen,
    propagiere,
    wuerde_zyklus_erzeugen,
)


def d(tag: int) -> date:
    """Tag 1 = 1. Juni 2026 -- Kalendertage, damit die Zahlen lesbar bleiben."""
    return date(2026, 6, tag)


def el(typ="schritt", start=None, ende=None, phase_id=None) -> PlanElement:
    return PlanElement(id=uuid.uuid4(), typ=typ, start_am=d(start) if start else None,
                       ende_am=d(ende) if ende else None, phase_id=phase_id)


def plan(*elemente: PlanElement) -> dict[uuid.UUID, PlanElement]:
    return {e.id: e for e in elemente}


def tage(e: PlanElement) -> tuple[int, int]:
    return e.start_am.day, e.ende_am.day


def kette():
    a, b, c = el(start=1, ende=5), el(start=6, ende=10), el(start=11, ende=15)
    return a, b, c, plan(a, b, c), [PlanKante(a.id, b.id), PlanKante(b.id, c.id)]


def test_kette_bei_konflikt_verschiebt_alles_nach_hinten():
    a, b, c, p, k = kette()
    geaendert = aendere_element(p, k, "bei_konflikt", a.id, start_am=d(4), ende_am=d(8))
    assert tage(a) == (4, 8)
    assert tage(b) == (9, 13)
    assert tage(c) == (14, 18)
    assert geaendert == {a.id, b.id, c.id}


def test_kette_bei_konflikt_laesst_puffer_stehen():
    a, b, c = el(start=1, ende=5), el(start=8, ende=12), el(start=20, ende=22)
    p, k = plan(a, b, c), [PlanKante(a.id, b.id), PlanKante(b.id, c.id)]
    geaendert = aendere_element(p, k, "bei_konflikt", a.id, start_am=d(3), ende_am=d(7))
    assert tage(b) == (8, 12)  # frueh = 8, kein Konflikt
    assert tage(c) == (20, 22)
    assert geaendert == {a.id}


def test_kette_bei_konflikt_verschiebt_nie_nach_vorne():
    a, b, c, p, k = kette()
    aendere_element(p, k, "bei_konflikt", a.id, start_am=d(1), ende_am=d(3))  # kuerzen
    assert tage(b) == (6, 10)
    assert tage(c) == (11, 15)


def test_kette_immer_zieht_auch_nach_vorne():
    a, b, c = el(start=3, ende=7), el(start=8, ende=12), el(start=13, ende=17)
    p, k = plan(a, b, c), [PlanKante(a.id, b.id), PlanKante(b.id, c.id)]
    aendere_element(p, k, "immer", a.id, start_am=d(1), ende_am=d(5))
    assert tage(b) == (6, 10)
    assert tage(c) == (11, 15)


def test_immer_erhaelt_puffer_beim_verschieben():
    a, b = el(start=1, ende=5), el(start=9, ende=12)
    p, k = plan(a, b), [PlanKante(a.id, b.id)]
    aendere_element(p, k, "immer", a.id, start_am=d(3), ende_am=d(7))
    assert tage(b) == (11, 14)


def test_verlaengern_schiebt_nachfolger_nur_bei_konflikt():
    a, b = el(start=1, ende=5), el(start=6, ende=10)
    p, k = plan(a, b), [PlanKante(a.id, b.id)]
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(8))
    assert tage(a) == (1, 8)
    assert tage(b) == (9, 13)


def test_verkuerzen_im_modus_immer_zieht_nachfolger_vor():
    a, b = el(start=1, ende=5), el(start=6, ende=10)
    p, k = plan(a, b), [PlanKante(a.id, b.id)]
    aendere_element(p, k, "immer", a.id, ende_am=d(3))
    assert tage(b) == (4, 8)


def test_diamant_nimmt_maximum_aller_vorgaenger():
    a, b, c, dd = el(start=1, ende=2), el(start=3, ende=4), el(start=3, ende=10), el(start=11, ende=12)
    p = plan(a, b, c, dd)
    k = [PlanKante(a.id, b.id), PlanKante(a.id, c.id), PlanKante(b.id, dd.id), PlanKante(c.id, dd.id)]
    aendere_element(p, k, "bei_konflikt", a.id, start_am=d(2), ende_am=d(3))
    assert tage(b) == (4, 5)
    assert tage(c) == (4, 11)
    assert tage(dd) == (12, 13)  # bestimmt durch c (Ende 11), nicht durch b


def test_diamant_unbewegter_vorgaenger_bleibt_massgeblich_im_modus_immer():
    a, b, c, dd = el(start=1, ende=2), el(start=3, ende=4), el(start=1, ende=9), el(start=10, ende=11)
    p = plan(a, b, c, dd)
    # c ist unabhaengig von a, D haengt an b und c
    k = [PlanKante(a.id, b.id), PlanKante(b.id, dd.id), PlanKante(c.id, dd.id)]
    aendere_element(p, k, "immer", a.id, start_am=d(1), ende_am=d(1))  # a kuerzer -> b/D wollen nach vorne
    assert tage(b) == (2, 3)
    assert tage(dd) == (10, 11)  # durch c (Ende 9) gehalten


def test_negativer_versatz_erlaubt_ueberlappung():
    a, b = el(start=1, ende=10), el(start=8, ende=12)
    p, k = plan(a, b), [PlanKante(a.id, b.id, versatz_tage=-3)]
    # fruehester Start = 10 + 1 - 3 = 8 -> kein Konflikt
    assert propagiere(p, k, "bei_konflikt", {}, erzwinge=[b.id]) == set()
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(12))
    assert tage(b) == (10, 14)


def test_meilenstein_als_vorgaenger_nachfolger_startet_am_selben_tag():
    m = el("meilenstein", start=5, ende=5)
    b = el(start=3, ende=6)
    p, k = plan(m, b), [PlanKante(m.id, b.id)]
    propagiere(p, k, "bei_konflikt", {}, erzwinge=[b.id])
    assert tage(b) == (5, 8)


def test_meilenstein_als_nachfolger_wird_verschoben_und_bleibt_eintaegig():
    a, m = el(start=1, ende=5), el("meilenstein", start=5, ende=5)
    p, k = plan(a, m), [PlanKante(a.id, m.id)]
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(7))
    assert tage(m) == (8, 8)


def test_meilenstein_start_aendern_zieht_ende_mit():
    m = el("meilenstein", start=5, ende=5)
    p = plan(m)
    aendere_element(p, [], "bei_konflikt", m.id, start_am=d(9))
    assert tage(m) == (9, 9)


def test_phase_verschieben_inklusive_kinder_und_nachfolger():
    ph = el("phase", start=1, ende=10)
    a, b = el(start=1, ende=4, phase_id=ph.id), el(start=5, ende=10, phase_id=ph.id)
    ausserhalb = el(start=11, ende=14)
    p = plan(ph, a, b, ausserhalb)
    k = [PlanKante(a.id, b.id), PlanKante(b.id, ausserhalb.id)]
    geaendert = aendere_element(p, k, "bei_konflikt", ph.id, start_am=d(4), ende_am=d(13))
    assert tage(a) == (4, 7)
    assert tage(b) == (8, 13)
    assert tage(ph) == (4, 13)
    assert tage(ausserhalb) == (14, 17)
    assert geaendert == {ph.id, a.id, b.id, ausserhalb.id}


def test_phase_ende_allein_oder_ungleiches_delta_ist_regelverstoss():
    ph = el("phase", start=1, ende=10)
    a = el(start=1, ende=10, phase_id=ph.id)
    p = plan(ph, a)
    with pytest.raises(ZeitplanRegelverstoss):
        aendere_element(p, [], "bei_konflikt", ph.id, ende_am=d(12))
    with pytest.raises(ZeitplanRegelverstoss):
        aendere_element(p, [], "bei_konflikt", ph.id, start_am=d(2), ende_am=d(12))


def test_phasenspanne_ist_min_max_der_kinder_und_leer_ist_none():
    ph, leer = el("phase"), el("phase", start=3, ende=4)
    a = el(start=5, ende=7, phase_id=ph.id)
    b = el("meilenstein", start=12, ende=12, phase_id=ph.id)
    ohne_datum = el(phase_id=ph.id)
    p = plan(ph, leer, a, b, ohne_datum)
    geaendert = aktualisiere_phasenspannen(p)
    assert tage(ph) == (5, 12)
    assert leer.start_am is None and leer.ende_am is None
    assert geaendert == {ph.id, leer.id}

    aendere_element(p, [], "bei_konflikt", a.id, start_am=d(1), ende_am=d(2))
    assert tage(ph) == (1, 12)


def test_zyklus_direkt_und_transitiv():
    a, b, c, p, k = kette()
    assert wuerde_zyklus_erzeugen(k, b.id, a.id)  # direkt (A->B existiert)
    assert wuerde_zyklus_erzeugen(k, c.id, a.id)  # transitiv (A->B->C)
    assert not wuerde_zyklus_erzeugen(k, a.id, c.id)  # Abkuerzung ist kein Kreis


def test_propagiere_erkennt_zyklus_in_den_daten():
    a, b = el(start=1, ende=2), el(start=3, ende=4)
    p = plan(a, b)
    with pytest.raises(ZeitplanZyklus):
        propagiere(p, [PlanKante(a.id, b.id), PlanKante(b.id, a.id)], "bei_konflikt", {a.id: 1})


def test_elemente_ohne_datum_nehmen_nicht_teil():
    a, b, c = el(start=1, ende=5), el(), el(start=6, ende=9)
    p = plan(a, b, c)
    k = [PlanKante(a.id, b.id), PlanKante(b.id, c.id)]
    aendere_element(p, k, "immer", a.id, start_am=d(10), ende_am=d(14))
    assert b.start_am is None
    assert tage(c) == (6, 9)  # Kette ueber das undatierte Element hinweg unterbrochen


def test_erstmals_datieren_und_ein_datum_genuegt():
    s = el()
    p = plan(s)
    aendere_element(p, [], "bei_konflikt", s.id, start_am=d(7))
    assert tage(s) == (7, 7)


def test_ende_vor_start_ist_regelverstoss():
    s = el(start=5, ende=8)
    with pytest.raises(ZeitplanRegelverstoss):
        aendere_element(plan(s), [], "bei_konflikt", s.id, start_am=d(9))


def test_explizit_gesetztes_element_wird_nicht_zurueckgeschoben():
    # Nutzer zieht B vor das Ende von A -- bewusst keine Korrektur an B selbst.
    a, b, c = el(start=1, ende=5), el(start=6, ende=10), el(start=11, ende=12)
    p, k = plan(a, b, c), [PlanKante(a.id, b.id), PlanKante(b.id, c.id)]
    aendere_element(p, k, "bei_konflikt", b.id, start_am=d(2), ende_am=d(6))
    assert tage(b) == (2, 6)
    assert tage(c) == (11, 12)


# --- Abhaengigkeitsarten ----------------------------------------------------


def kante(a, b, art, versatz=0):
    return PlanKante(a.id, b.id, versatz, art)


def test_anfang_anfang_folgt_dem_start_des_vorgaengers():
    a, b = el(start=1, ende=5), el(start=3, ende=6)
    p, k = plan(a, b), [kante(a, b, "anfang_anfang")]
    aendere_element(p, k, "bei_konflikt", a.id, start_am=d(10), ende_am=d(14))
    assert tage(b) == (10, 13)  # Dauer bleibt


def test_anfang_anfang_mit_versatz_und_verlaengern_aendert_nichts():
    a, b = el(start=5, ende=8), el(start=3, ende=4)
    p, k = plan(a, b), [kante(a, b, "anfang_anfang", 2)]
    propagiere(p, k, "bei_konflikt", {a.id: 0})
    assert tage(b) == (7, 8)
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(20))  # nur Ende: Start bleibt
    assert tage(b) == (7, 8)


def test_anfang_anfang_immer_nutzt_start_delta_nicht_ende_delta():
    a, b = el(start=3, ende=7), el(start=3, ende=5)
    p, k = plan(a, b), [kante(a, b, "anfang_anfang")]
    aendere_element(p, k, "immer", a.id, ende_am=d(12))  # Start unveraendert -> b bleibt
    assert tage(b) == (3, 5)
    aendere_element(p, k, "immer", a.id, start_am=d(1), ende_am=d(5))  # Start -2 -> b -2
    assert tage(b) == (1, 3)


def test_anfang_anfang_bei_konflikt_zieht_nicht_nach_vorne():
    a, b = el(start=3, ende=7), el(start=3, ende=5)
    p, k = plan(a, b), [kante(a, b, "anfang_anfang")]
    aendere_element(p, k, "bei_konflikt", a.id, start_am=d(1), ende_am=d(5))
    assert tage(b) == (3, 5)


def test_ende_ende_schiebt_nachfolger_als_ganzes_bis_ende_passt():
    a, b = el(start=1, ende=5), el(start=3, ende=7)
    p, k = plan(a, b), [kante(a, b, "ende_ende")]
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(9))
    assert tage(b) == (5, 9)
    aendere_element(p, [kante(a, b, "ende_ende", 1)], "bei_konflikt", a.id, ende_am=d(9))
    assert tage(b) == (6, 10)


def test_ende_ende_ohne_konflikt_bleibt_stehen_und_immer_zieht_mit():
    a, b = el(start=1, ende=5), el(start=3, ende=9)
    p, k = plan(a, b), [kante(a, b, "ende_ende")]
    aendere_element(p, k, "bei_konflikt", a.id, ende_am=d(7))
    assert tage(b) == (3, 9)
    aendere_element(p, k, "immer", a.id, ende_am=d(10))  # +3
    assert tage(b) == (6, 12)
    aendere_element(p, k, "immer", a.id, ende_am=d(8))  # -2
    assert tage(b) == (4, 10)


def test_gemischte_vorgaenger_strengste_bedingung_gewinnt():
    a, b = el(start=1, ende=5), el(start=4, ende=12)
    c = el(start=2, ende=3)
    p = plan(a, b, c)
    k = [kante(a, c, "ende_anfang"), kante(b, c, "ende_ende")]
    # EA(a): Start >= 6; EE(b): Ende >= 12 -> Start >= 11 bei Dauer 2
    propagiere(p, k, "bei_konflikt", {}, erzwinge=[c.id])
    assert tage(c) == (11, 12)


def test_gemischte_vorgaenger_aa_strenger_als_ea():
    a, b, c = el(start=1, ende=5), el(start=20, ende=25), el(start=2, ende=4)
    p = plan(a, b, c)
    k = [kante(a, c, "ende_anfang"), kante(b, c, "anfang_anfang", 1)]
    propagiere(p, k, "bei_konflikt", {}, erzwinge=[c.id])
    assert tage(c) == (21, 23)


def test_meilenstein_als_vorgaenger_bei_aa_und_ee():
    m = el("meilenstein", 10, 10)
    s1, s2 = el(start=1, ende=3), el(start=1, ende=3)
    p = plan(m, s1, s2)
    k = [kante(m, s1, "anfang_anfang"), kante(m, s2, "ende_ende")]
    propagiere(p, k, "bei_konflikt", {}, erzwinge=[s1.id, s2.id])
    assert tage(s1) == (10, 12)
    assert tage(s2) == (8, 10)


def test_meilenstein_als_nachfolger_bei_ende_ende_bleibt_eintaegig():
    a, m = el(start=1, ende=9), el("meilenstein", 5, 5)
    p, k = plan(a, m), [kante(a, m, "ende_ende")]
    propagiere(p, k, "bei_konflikt", {a.id: 0})
    assert tage(m) == (9, 9)


def test_zyklus_ist_unabhaengig_von_der_art():
    a, b = el(start=1, ende=2), el(start=3, ende=4)
    k = [kante(a, b, "anfang_anfang")]
    assert wuerde_zyklus_erzeugen(k, b.id, a.id)
    p = plan(a, b)
    with pytest.raises(ZeitplanZyklus):
        propagiere(p, k + [kante(b, a, "ende_ende")], "bei_konflikt", {a.id: 0})


def test_fester_meilenstein_wird_von_propagation_nicht_verschoben():
    a, m, s = el(start=1, ende=5), el("meilenstein", 3, 3), el(start=4, ende=6)
    p = plan(a, m, s)
    k = [kante(a, m, "ende_anfang"), kante(m, s, "ende_anfang")]
    propagiere(p, k, "bei_konflikt", {a.id: 0}, fest=[m.id])
    assert tage(m) == (3, 3)
    assert tage(s) == (4, 6)  # m selbst unveraendert, s ist an m gemessen -> kein Konflikt
