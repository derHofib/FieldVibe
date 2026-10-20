from datetime import date

from sqlalchemy import select

from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.material import Material, MaterialBestand, MaterialBewegung
from app.models.pruefzyklus import Pruefzyklus
from app.models.standort import Standort
from tests.test_datenimport import PW, _admin, analyse, csv_bytes, kompletter_lauf


async def _lauf_ausfuehren(client, kopf, entitaet, text, **optionen):
    a, k, p = await kompletter_lauf(client, kopf, entitaet, csv_bytes(text), **optionen)
    assert p.status_code == 200, p.text
    r = await client.post(f"/api/import/{a['import_lauf_id']}/ausfuehren", headers=kopf, json=k)
    assert r.status_code == 200, r.text
    return a, k, p.json(), r.json()


ANLAGEN = (
    "Kundennummer;Standort;Anlagenbezeichnung;Hersteller;Seriennummer;Baujahr;Straße;PLZ;Ort;Letzte Prüfung;Prüfintervall (Monate)\n"
    "K-1;Werk 1;Hauptverteilung;Siemens;SN-1;2015;Hauptstr. 1;01067;Dresden;15.03.2025;12\n"
    "K-1;Werk 1;Notlicht;Hella;SN-2;;;;;2025-06-02;6\n"
    "K-1;;Einzelgeraet;;;;;;;;\n"
    ";;;;;;;;;;\n"
    "K-9;Werk;X;;;;;;;;\n"
    "K-1;Werk 1;Hauptverteilung;Siemens;SN-1;;;;;;\n"
)


async def test_anlagen_import_mit_standort_und_pruefzyklus(client, make_mandant, make_user, make_kunde):
    mandant, _, kopf = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="Kunde Eins", kundennummer="K-1")
    a, k, probe, erg = await _lauf_ausfuehren(client, kopf, "anlagen", ANLAGEN)
    z = {x["zeile"]: x for x in probe["zeilen"]}
    assert z[6]["status"] == "fehler" and "unbekannt" in z[6]["meldungen"][0]
    assert z[7]["dublette_art"] == "seriennummer_kunde"
    assert erg["zusammenfassung"] == probe["zusammenfassung"]
    async with system_session() as s:
        standorte = (await s.execute(select(Standort).where(Standort.kunde_id == kunde.id))).scalars().all()
        assert len(standorte) == 1 and standorte[0].adresse["plz"] == "01067"
        anlagen = {x.bezeichnung: x for x in (await s.execute(select(Anlage).where(Anlage.kunde_id == kunde.id))).scalars()}
        assert set(anlagen) == {"Hauptverteilung", "Notlicht", "Einzelgeraet"}
        assert anlagen["Notlicht"].standort_id == standorte[0].id
        assert anlagen["Notlicht"].adresse["ort"] == "Dresden"  # vom Standort uebernommen
        assert anlagen["Hauptverteilung"].notiz == "Baujahr: 2015"
        assert anlagen["Einzelgeraet"].standort_id is None
        zyklen = (await s.execute(select(Pruefzyklus))).scalars().all()
        assert len(zyklen) == 2
        pz = next(x for x in zyklen if x.anlage_id == anlagen["Hauptverteilung"].id)
        assert pz.intervall_wert == 12 and pz.letzte_pruefung_am.date() == date(2025, 3, 15)
        assert pz.naechste_pruefung_am.date() == date(2026, 3, 15)
    # Zweiter Import derselben Datei: alles Dubletten, nichts neu
    _, _, p2, _ = await _lauf_ausfuehren(client, kopf, "anlagen", ANLAGEN)
    assert p2["zusammenfassung"]["anlegen"] == 0


async def test_anlagen_kundenzuordnung_mehrdeutig(client, make_mandant, make_user, make_kunde):
    mandant, _, kopf = await _admin(client, make_mandant, make_user)
    await make_kunde(mandant=mandant, name="Müller", kundennummer="K-1")
    await make_kunde(mandant=mandant, name="Mueller", kundennummer="K-2")
    await make_kunde(mandant=mandant, name="Einzig", kundennummer="K-3")
    text = "Kundenname;Anlagenbezeichnung\nMüller;A\nEinzig;B\nNiemand;C\n"
    _, _, p = await kompletter_lauf(client, kopf, "anlagen", csv_bytes(text))
    z = {x["zeile"]: x for x in p.json()["zeilen"]}
    assert z[2]["status"] == "fehler" and "mehrdeutig" in z[2]["meldungen"][0]
    assert z[3]["status"] == "neu"
    assert z[4]["status"] == "fehler" and "unbekannt" in z[4]["meldungen"][0]


async def test_anlagen_pruefdaten_fehler_und_dublette_aktualisieren(client, make_mandant, make_user, make_kunde, make_anlage):
    mandant, _, kopf = await _admin(client, make_mandant, make_user)
    kunde = await make_kunde(mandant=mandant, name="K", kundennummer="K-1")
    await make_anlage(mandant=mandant, kunde=kunde, bezeichnung="Alt", seriennummer="S1")
    text = (
        "Kundennummer;Bezeichnung;Seriennummer;Hersteller;Prüfintervall;Letzte Prüfung\n"
        "K-1;Neu;S9;;abc;\n"
        "K-1;Neu2;S8;;6;31.02.2025\n"
        "K-1;Alt;S1;Bosch;12;01.01.2025\n"
    )
    a, k, p = await kompletter_lauf(client, kopf, "anlagen", csv_bytes(text), dubletten_aktionen={"seriennummer_kunde": "aktualisieren"})
    z = {x["zeile"]: x for x in p.json()["zeilen"]}
    assert z[2]["status"] == "fehler" and z[3]["status"] == "fehler"
    assert z[4]["aktion"] == "aktualisieren"
    r = await client.post(f"/api/import/{a['import_lauf_id']}/ausfuehren", headers=kopf, json=k)
    assert r.json()["zusammenfassung"]["aktualisieren"] == 1
    async with system_session() as s:
        alt = (await s.execute(select(Anlage).where(Anlage.bezeichnung == "Alt"))).scalar_one()
        assert alt.hersteller == "Bosch"
        assert len((await s.execute(select(Pruefzyklus).where(Pruefzyklus.anlage_id == alt.id))).scalars().all()) == 1


async def test_anlagen_rueckgaengig(client, make_mandant, make_user, make_kunde):
    mandant, _, kopf = await _admin(client, make_mandant, make_user)
    await make_kunde(mandant=mandant, name="K", kundennummer="K-1")
    a, _, _, _ = await _lauf_ausfuehren(client, kopf, "anlagen", ANLAGEN)
    r = await client.post(f"/api/import/{a['import_lauf_id']}/rueckgaengig", headers=kopf)
    assert r.status_code == 200, r.text
    zr = r.json()["ergebnis"]["rueckgaengig"]["zurueckgesetzt"]
    assert zr == {"pruefzyklus": 2, "anlage": 3, "standort": 1}
    async with system_session() as s:
        assert all(x.geloescht_am is not None for x in (await s.execute(select(Anlage).where(Anlage.objekttyp == "kundenanlage"))).scalars())
    # im Papierkorb wiederherstellbar
    from app.services import papierkorb_service

    async with system_session() as s:
        papierkorb = await papierkorb_service.list_papierkorb(s, mandant_id=mandant.id)
    assert {e.entity_typ for e in papierkorb} == {"anlage", "standort", "pruefzyklus"}


MATERIAL = (
    "Art-Nr;Bezeichnung;ME;VK netto;EK;Bestand\n"
    "A-1;Kabel NYM 3x1,5;m;1,25;0,80;250\n"
    "A-2;Schalter;Stück;1.234,50;;\n"
    ";Ohne Nummer;;;;\n"
    "A-1;Doppelt;Stk;2;;\n"
    "A-3;Negativ;Stk;-5;;\n"
)


async def test_material_import(client, make_mandant, make_user):
    mandant, _, kopf = await _admin(client, make_mandant, make_user)
    a, k, probe, erg = await _lauf_ausfuehren(client, kopf, "material", MATERIAL)
    z = {x["zeile"]: x for x in probe["zeilen"]}
    assert z[5]["dublette_art"] == "artikelnummer" and z[6]["status"] == "fehler"
    assert erg["zusammenfassung"]["anlegen"] == 3
    async with system_session() as s:
        m = {x.bezeichnung: x for x in (await s.execute(select(Material).where(Material.mandant_id == mandant.id))).scalars()}
        assert str(m["Schalter"].einzelpreis) == "1234.50" and m["Schalter"].einheit == "Stk"
        kabel = m["Kabel NYM 3x1,5"]
        assert str(kabel.einzelpreis) == "1.25" and kabel.einheit == "m"
        bestand = (await s.execute(select(MaterialBestand).where(MaterialBestand.material_id == kabel.id))).scalar_one()
        assert bestand.menge == 250
        bew = (await s.execute(select(MaterialBewegung).where(MaterialBewegung.material_id == kabel.id))).scalar_one()
        assert bew.typ == "eingang"
    # EK bleibt unzugeordnet
    assert [v for v in (await analyse(client, kopf, "material", csv_bytes(MATERIAL))).json()["vorschlag"] if v["feld"] == "einzelpreis"][0]["spalte"] == 3
    r = await client.post(f"/api/import/{a['import_lauf_id']}/rueckgaengig", headers=kopf)
    assert r.json()["ergebnis"]["rueckgaengig"]["zurueckgesetzt"] == {"material": 3}
