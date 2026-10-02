"""Zeitplan Phase 3 -- reine Logik: kritischer Pfad, Straffen."""
import uuid
from datetime import date

from app.services.zeitplan_service import (
    PlanElement,
    PlanKante,
    berechne_kritischen_pfad,
    straffe_plan,
)


def d(tag: int) -> date:
    return date(2026, 6, 1 + tag - 1) if tag <= 30 else date(2026, 7, tag - 30)


def el(start=None, ende=None, typ="schritt", phase_id=None) -> PlanElement:
    ende = ende if ende is not None else start
    return PlanElement(
        id=uuid.uuid4(), typ=typ, start_am=d(start) if start else None, ende_am=d(ende) if ende else None,
        phase_id=phase_id,
    )


def plan(*es: PlanElement) -> dict:
    return {e.id: e for e in es}


def k(a, b, art="ende_anfang", versatz=0) -> PlanKante:
    return PlanKante(a.id, b.id, versatz, art)


def tage(e: PlanElement) -> tuple[int, int]:
    return e.start_am.day, e.ende_am.day


# --- kritischer Pfad ---------------------------------------------------------


def test_cpm_kette_alle_kritisch():
    a, b, c = el(1, 5), el(6, 10), el(11, 15)
    r = berechne_kritischen_pfad(plan(a, b, c), [k(a, b), k(b, c)])
    assert r.puffer == {a.id: 0, b.id: 0, c.id: 0}
    assert r.kritisch == {a.id, b.id, c.id}
    assert r.kritische_kanten == {(a.id, b.id), (b.id, c.id)}


def test_cpm_parallelzweig_hat_puffer():
    a, b, c, x = el(1, 5), el(6, 10), el(11, 15), el(6, 7)
    r = berechne_kritischen_pfad(plan(a, b, c, x), [k(a, b), k(b, c), k(a, x), k(x, c)])
    # x darf bis Tag 10 enden (c startet 11) -> spaetester Start 9, Ist 6 -> 3 Tage
    assert r.puffer[x.id] == 3
    assert x.id not in r.kritisch
    assert (a.id, x.id) not in r.kritische_kanten
    assert (a.id, b.id) in r.kritische_kanten


def test_cpm_luecke_im_plan_erzeugt_puffer_ohne_pfad():
    a, b = el(1, 5), el(8, 10)
    r = berechne_kritischen_pfad(plan(a, b), [k(a, b)])
    assert r.puffer[a.id] == 2 and r.puffer[b.id] == 0
    assert r.kritisch == {b.id}
    assert r.kritische_kanten == set()  # Kante nicht "eng"


def test_cpm_anfang_anfang():
    a, b = el(1, 10), el(3, 12)
    r = berechne_kritischen_pfad(plan(a, b), [k(a, b, "anfang_anfang", 2)])
    assert r.puffer == {a.id: 0, b.id: 0}
    assert r.kritische_kanten == {(a.id, b.id)}


def test_cpm_aa_vorgaenger_laenger_als_nachfolger_wird_durch_projektende_begrenzt():
    a, b = el(1, 20), el(1, 5)
    r = berechne_kritischen_pfad(plan(a, b), [k(a, b, "anfang_anfang")])
    assert r.puffer[a.id] == 0  # endet am Projektende
    assert r.puffer[b.id] == 15


def test_cpm_ende_ende_und_negativer_versatz():
    a, b = el(1, 10), el(5, 10)
    r = berechne_kritischen_pfad(plan(a, b), [k(a, b, "ende_ende")])
    assert r.puffer[b.id] == 0 and r.puffer[a.id] == 0
    assert r.kritische_kanten == {(a.id, b.id)}
    # Ende->Anfang mit negativem Versatz: b startet 2 Tage vor Ende von a
    a2, b2 = el(1, 10), el(9, 14)
    r2 = berechne_kritischen_pfad(plan(a2, b2), [k(a2, b2, versatz=-2)])
    assert r2.kritisch == {a2.id, b2.id}
    assert r2.kritische_kanten == {(a2.id, b2.id)}


def test_cpm_meilenstein_am_selben_tag():
    a = el(1, 5)
    m = el(5, 5, typ="meilenstein")  # Meilenstein darf am Ende-Tag des Vorgaengers liegen
    b = el(5, 8)
    r = berechne_kritischen_pfad(plan(a, m, b), [k(a, m), k(m, b)])
    assert r.puffer[m.id] == 0
    assert r.kritisch >= {m.id, b.id}


def test_cpm_mehrere_endpunkte_spaetester_bestimmt_projektende():
    a, b, c = el(1, 5), el(6, 10), el(6, 20)
    r = berechne_kritischen_pfad(plan(a, b, c), [k(a, b), k(a, c)])
    assert r.puffer[c.id] == 0 and r.puffer[a.id] == 0
    assert r.puffer[b.id] == 10  # Senke b darf bis Projektende (Tag 20) enden
    assert b.id not in r.kritisch


def test_cpm_ignoriert_phasen_und_undatierte_und_negativer_puffer():
    ph = el(1, 30, typ="phase")
    ohne = el()
    a, b = el(1, 5), el(3, 8)  # b startet vor Ende von a -> bewusst verletzt
    r = berechne_kritischen_pfad(plan(ph, ohne, a, b), [k(a, b), k(ph, a), k(ohne, b)])
    assert ph.id not in r.puffer and ohne.id not in r.puffer
    assert r.puffer[a.id] < 0  # Verletzung zeigt sich als negativer Puffer
    assert {a.id, b.id} <= r.kritisch


def test_cpm_leerer_plan():
    r = berechne_kritischen_pfad({}, [])
    assert r.puffer == {} and r.kritisch == set()


# --- Straffen ---------------------------------------------------------------


def test_straffen_zieht_nach_vorne_und_haelt_dauer():
    a, b, c = el(1, 5), el(10, 12), el(20, 25)
    p = plan(a, b, c)
    geaendert = straffe_plan(p, [k(a, b), k(b, c)])
    assert geaendert == {b.id, c.id}
    assert tage(a) == (1, 5) and tage(b) == (6, 8) and tage(c) == (9, 14)


def test_straffen_beruecksichtigt_alle_vorgaenger_und_arten():
    a, b, x = el(1, 5), el(1, 3), el(20, 22)
    p = plan(a, b, x)
    straffe_plan(p, [k(a, x), k(b, x, "ende_ende", 4)])
    # EA: ab 6; EE: ende >= 3+4=7 -> start >= 5; strengere gewinnt (6)
    assert tage(x) == (6, 8)


def test_straffen_ohne_vorgaenger_bleibt_und_gesperrte_bleiben():
    a, b, m = el(5, 8), el(20, 22), el(25, 25, typ="meilenstein")
    p = plan(a, b, m)
    straffe_plan(p, [k(a, b), k(b, m)], fest={m.id})
    assert tage(a) == (5, 8)
    assert tage(b) == (9, 11)
    assert tage(m) == (25, 25)


def test_straffen_phasenfilter_nur_diese_phase_angefasst():
    ph1, ph2 = el(typ="phase"), el(typ="phase")
    a = el(1, 5, phase_id=ph1.id)
    b = el(10, 12, phase_id=ph1.id)
    c = el(20, 22, phase_id=ph2.id)
    p = plan(ph1, ph2, a, b, c)
    straffe_plan(p, [k(a, b), k(b, c)], phase_id=ph1.id)
    assert tage(b) == (6, 8)
    assert tage(c) == (20, 22)  # andere Phase unberuehrt
    assert (p[ph1.id].start_am, p[ph1.id].ende_am) == (d(1), d(8))  # Spanne neu


def test_straffen_phasenfilter_vorgaenger_ausserhalb_ist_randbedingung():
    ph1, ph2 = el(typ="phase"), el(typ="phase")
    a = el(1, 10, phase_id=ph2.id)  # ausserhalb, bleibt
    b = el(25, 27, phase_id=ph1.id)
    p = plan(ph1, ph2, a, b)
    straffe_plan(p, [k(a, b)], phase_id=ph1.id)
    assert tage(b) == (11, 13)
