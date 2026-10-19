"""DATEV-Export und UStVA fuer Storno, Gutschrift, Abschlag und Schlussrechnung.

Storno-Belege und Gutschriften tragen negative Betraege und sind Gegenbuchungen:
gleicher Betrag (positiv), gleiche Konten, aber Soll/Haben-Kennzeichen "H".
Vorher stand fuer alles ein festes "S", ein Storno erschien wie eine zweite
Normalbuchung und der Umsatz war doppelt gebucht."""
import csv
import io

from tests.test_rechnungsarten import (
    GRUPPEN_POSITIONEN,
    _abschlag_versendet,
    _admin,
    _angebot,
    _aus_angebot,
    _d,
    _gutschrift,
    _ok,
    _rechnung_direkt,
    _versenden,
    _versendete_rechnung,
)

_ZEITRAUM = "von=2020-01-01&bis=2030-12-31"
_KONTEN = {
    "buchhaltung": {
        "erloeskonten": {"Z:0.00": {"konto": "8101", "bu": "11"}},
    }
}


async def _datev(client, h) -> list[list[str]]:
    antwort = await client.get(f"/api/auswertung/datev-export?{_ZEITRAUM}", headers=h)
    assert antwort.status_code == 200, antwort.text
    return list(csv.reader(io.StringIO(antwort.text), delimiter=";"))[2:]


def _spalten(zeilen, *indizes):
    return [tuple(z[i] for i in indizes) for z in zeilen]


async def test_normale_rechnung_bleibt_soll_wie_bisher(client, make_mandant, make_user, make_kunde):
    # Golden: eine normale Rechnung wird weiterhin als Soll mit Betrag, Debitor und Erloeskonto gebucht.
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    rechnung = await _versendete_rechnung(client, h, kunde, [{"beschreibung": "Material", "einzelpreis": "100"}])
    [zeile] = await _datev(client, h)
    assert (zeile[0], zeile[1], zeile[2], zeile[4], zeile[5], zeile[7]) == (
        "119,00",
        "S",
        "EUR",
        "8400",
        "3",
        rechnung["rechnungsnummer"],
    )
    assert zeile[9] == f"Rechnung {rechnung['rechnungsnummer']} {kunde.name}"


async def test_storno_ist_gegenbuchung_mit_haben(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=_KONTEN)
    original = await _versendete_rechnung(client, h, kunde, GRUPPEN_POSITIONEN, leistungsdatum="2026-07-15")
    storno = await _ok(await client.post(f"/api/rechnungen/{original['id']}/storno", headers=h))
    zeilen = await _datev(client, h)
    # Je Rechnung eine Zeile je Steuergruppe (19 %, 7 %, 0 % PV) -- Original Soll, Storno Haben.
    original_zeilen = [z for z in zeilen if z[7] == original["rechnungsnummer"]]
    storno_zeilen = [z for z in zeilen if z[7] == storno["rechnungsnummer"]]
    assert len(original_zeilen) == len(storno_zeilen) == 3
    assert {z[1] for z in original_zeilen} == {"S"} and {z[1] for z in storno_zeilen} == {"H"}
    # Gleiche Betraege (positiv), Konten und BU-Schluessel in gleicher Reihenfolge.
    assert _spalten(original_zeilen, 0, 3, 4, 5) == _spalten(storno_zeilen, 0, 3, 4, 5)


async def test_gutschrift_ist_gegenbuchung_mit_haben(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, firmendaten=_KONTEN)
    original = await _versendete_rechnung(client, h, kunde, GRUPPEN_POSITIONEN)
    leistung, material, _ = original["positionen"]
    gutschrift = await _ok(
        await _gutschrift(
            client,
            h,
            original["id"],
            positionen=[{"position_id": leistung["id"], "menge": "1"}, {"position_id": material["id"], "menge": "2"}],
        )
    )
    zeilen = await _datev(client, h)
    gs_zeilen = [z for z in zeilen if z[7] == gutschrift["rechnungsnummer"]]
    # 100 netto 19 % -> 119,00; 100 netto 7 % -> 107,00 (positiv, Haben), Konten wie die Ursprungsrechnung.
    assert _spalten(gs_zeilen, 0, 1, 4, 5) == [("119,00", "H", "8400", "3"), ("107,00", "H", "8300", "2")]
    assert all(z[9].startswith("Gutschrift ") for z in gs_zeilen)
    ursprung = [z for z in zeilen if z[7] == original["rechnungsnummer"]]
    assert {z[3] for z in ursprung} == {z[3] for z in gs_zeilen}  # gleiches Debitorenkonto
    assert {z[1] for z in ursprung} == {"S"}


async def test_abschlag_und_schluss_sind_normale_buchungen(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)  # 1500 netto, 1785 brutto
    abschlag = await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    schluss = await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    zeilen = await _datev(client, h)
    assert _spalten(zeilen, 0, 1, 4, 7) == [
        ("535,50", "S", "8400", abschlag["rechnungsnummer"]),
        ("1249,50", "S", "8400", schluss["rechnungsnummer"]),
    ]
    # Abschlag + Schluss = Angebot.
    assert _d(abschlag["betrag_brutto"]) + _d(schluss["betrag_brutto"]) == _d(angebot["gesamt_brutto"])


async def test_schluss_mit_negativer_steuergruppe_wird_haben(client, make_mandant, make_user, make_kunde, make_vorgang):
    """Abschlag ueber den 7-%-Anteil groesser als dessen Rest: die Gruppe wird negativ."""
    mandant, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, titel="Umbau")
    abschlag = await _rechnung_direkt(
        client,
        h,
        kunde,
        [{"beschreibung": "Abschlag 7", "einzelpreis": "300", "steuer_satz": "7"}],
        rechnungsart="abschlag",
        vorgang_id=str(vorgang.id),
    )
    await _versenden(client, h, abschlag["id"])
    schluss = await _rechnung_direkt(
        client,
        h,
        kunde,
        [
            {"beschreibung": "Leistung 19", "einzelpreis": "1000"},
            {"beschreibung": "Material 7", "einzelpreis": "200", "steuer_satz": "7"},
        ],
        vorgang_id=str(vorgang.id),
    )
    await _ok(await client.post(f"/api/rechnungen/{schluss['id']}/abschlaege-anrechnen", headers=h), 200)
    await _versenden(client, h, schluss["id"])
    zeilen = [z for z in await _datev(client, h) if z[7] == schluss["rechnungsnummer"]]
    # 19 %: 1190 Soll; 7 %: (200 - 300) netto -> -107 brutto -> 107 Haben.
    assert _spalten(zeilen, 0, 1, 4) == [("1190,00", "S", "8400"), ("107,00", "H", "8300")]


async def test_ust_va_summen_mit_storno_und_gutschrift(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    eins = await _versendete_rechnung(client, h, kunde)  # 1000 netto
    await _ok(await _gutschrift(client, h, eins["id"], positionen=[{"position_id": eins["positionen"][0]["id"], "menge": "3"}]))
    zwei = await _versendete_rechnung(client, h, kunde)  # 1000 netto, wird storniert
    await _ok(await client.post(f"/api/rechnungen/{zwei['id']}/storno", headers=h))
    await _versendete_rechnung(client, h, kunde)  # 1000 netto

    ustva = (await client.get(f"/api/auswertung/ust-va?{_ZEITRAUM}", headers=h)).json()
    # 1000 - 300 + (1000 - 1000) + 1000 = 1700 netto, 323,00 USt.
    assert ustva["umsatzsteuer_saetze"] == [{"satz": "19.00", "netto": "1700.00", "steuer": "323.00"}]
    assert ustva["summe_umsatzsteuer"] == "323.00"


async def test_ust_va_abschlag_plus_schluss_ergibt_den_umsatz_des_angebots(client, make_mandant, make_user, make_kunde):
    _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _abschlag_versendet(client, h, angebot["id"], abschlag_prozent="30")
    await _versenden(client, h, (await _ok(await _aus_angebot(client, h, angebot["id"], "schluss")))["id"])
    ustva = (await client.get(f"/api/auswertung/ust-va?{_ZEITRAUM}", headers=h)).json()
    assert ustva["umsatzsteuer_saetze"] == [{"satz": "19.00", "netto": "1500.00", "steuer": "285.00"}]
