"""Vorgang-Uebernahme in den Rechnungsentwurf (POST .../vorgaenge): Vorschlaege
mit IDs, Teilauswahl, Material-Sperre wie bei Zeit, Gruppendarstellung."""
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import system_session
from app.models.anlage import Anlage
from app.models.material import Material, MaterialBestand, MaterialBewegung, MaterialVerwendung
from tests.conftest import auth_headers, login
from tests.test_rechnungen_sammelrechnung import (
    _daten_zwei_vorgaenge,
    _rechnung_anlegen,
    _setup,
    _svs,
    _uebernehmen,
    _zeit,
    sammelrechnung,
)


async def _material(mandant, vorgang, user, *, bezeichnung: str, menge: str, preis: str, verwendungen: int = 1):
    """Legt ein Material samt Verwendung(en) am Vorgang an. Der Bestand wird
    bewusst nicht ueber die Route gebucht -- die Tests pruefen, dass die
    Sperre daran nichts aendert."""
    async with system_session() as session:
        lager = (
            await session.execute(
                select(Anlage).where(Anlage.mandant_id == mandant.id, Anlage.objekttyp == "lager")
            )
        ).scalars().one()
        material = Material(
            mandant_id=mandant.id, bezeichnung=bezeichnung, einheit="Stk", einzelpreis=Decimal(preis)
        )
        session.add(material)
        await session.flush()
        session.add(MaterialBestand(mandant_id=mandant.id, material_id=material.id, lager_id=lager.id, menge=Decimal("100")))
        ids = []
        for _ in range(verwendungen):
            v = MaterialVerwendung(
                mandant_id=mandant.id,
                material_id=material.id,
                lager_id=lager.id,
                vorgang_id=vorgang.id,
                menge=Decimal(menge),
                verwendet_von=user.id,
            )
            session.add(v)
            await session.flush()
            ids.append(v.id)
        return material.id, ids


async def _verwendungen(*ids):
    async with system_session() as session:
        return [await session.get(MaterialVerwendung, i) for i in ids]


async def _bestand_stand(material_id):
    async with system_session() as session:
        bestand = (
            await session.execute(select(MaterialBestand.menge).where(MaterialBestand.material_id == material_id))
        ).scalar_one()
        bewegungen = (
            await session.execute(select(MaterialBewegung.id).where(MaterialBewegung.material_id == material_id))
        ).scalars().all()
        return bestand, len(bewegungen)


async def _abrechenbar(client, token, kunde):
    resp = await client.get(f"/api/rechnungen/abrechenbare-vorgaenge?kunde_id={kunde.id}", headers=auth_headers(token))
    assert resp.status_code == 200
    return {v["vorgang_id"]: v for v in resp.json()}


async def _loeschen_user_token(client, make_user, mandant):
    operativ = await make_user(mandant=mandant, role="loesch_operativ", password="pw-123456")
    return await login(client, operativ.email, "pw-123456")


@pytest.mark.asyncio
async def test_vorschlaege_endpoint_liefert_alle_quellen_mit_ids(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        svs = await _svs(session, mandant)
        await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=1)
        await _zeit(session, mandant=mandant, vorgang=vb, techniker=admin, stunden=3, lv_position_id=svs.id)
    mat_id, _ = await _material(mandant, vb, admin, bezeichnung="Dose", menge="2", preis="4.50")
    rechnung = await _rechnung_anlegen(client, token, kunde)

    resp = await client.get(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge/{vb.id}/vorschlaege", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    je_quelle = {v["quelle"]: v for v in resp.json()}
    assert set(je_quelle) == {"material", "zeit", "leistung"}
    assert je_quelle["material"]["material_id"] == str(mat_id)
    assert je_quelle["material"]["menge"] == "2.00" and je_quelle["material"]["einzelpreis"] == "4.50"
    assert je_quelle["leistung"]["lv_position_id"] == str(svs.id)
    assert je_quelle["zeit"]["lv_position_id"] is None and je_quelle["zeit"]["material_id"] is None


@pytest.mark.asyncio
async def test_vorschlaege_endpoint_validierung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    anderer_kunde = await make_kunde(mandant=mandant)
    fremd = await make_vorgang(mandant=mandant, kunde=anderer_kunde)
    headers = auth_headers(token)
    rechnung = await _rechnung_anlegen(client, token, kunde)

    r = await client.get(f"/api/rechnungen/{rechnung['id']}/vorgaenge/{fremd.id}/vorschlaege", headers=headers)
    assert r.status_code == 400

    versendet = await client.patch(f"/api/rechnungen/{rechnung['id']}", headers=headers, json={"status": "versendet"})
    assert versendet.status_code == 200
    r = await client.get(f"/api/rechnungen/{rechnung['id']}/vorgaenge/{va.id}/vorschlaege", headers=headers)
    assert r.status_code == 400
    r = await client.post(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge",
        headers=headers,
        json={"vorgang_id": str(va.id), "auswahl": [{"quelle": "zeit"}]},
    )
    assert r.status_code == 400

    r = await client.get(
        f"/api/rechnungen/00000000-0000-0000-0000-000000000000/vorgaenge/{va.id}/vorschlaege", headers=headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_teilauswahl_sperrt_nur_gewaehltes(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=va, techniker=admin, stunden=2)
    kabel_id, kabel_v = await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1.20", verwendungen=2)
    dose_id, dose_v = await _material(mandant, va, admin, bezeichnung="Dose", menge="1", preis="4.50")
    bestand_vorher = await _bestand_stand(kabel_id)
    rechnung = await _rechnung_anlegen(client, token, kunde)

    resp = await _uebernehmen(
        client, token, rechnung["id"], va, stundensatz="80",
        nur=lambda v: v["quelle"] == "zeit" or v["material_id"] == str(kabel_id),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Vorschlagsreihenfolge: Material vor Zeit
    assert [(p["quelle"], p["beschreibung"]) for p in body["positionen"]] == [("material", "Kabel"), ("zeit", "Arbeitszeit")]
    kabel_pos, zeit_pos = body["positionen"]
    assert zeit_pos["einzelpreis"] == "80.00" and zeit_pos["vorgang_id"] == str(va.id)
    assert kabel_pos["menge"] == "10.00" and kabel_pos["material_id"] == str(kabel_id)
    assert kabel_pos["vorgang_id"] == str(va.id)

    for v in await _verwendungen(*kabel_v):
        assert v.abrechnungsstatus == "abgerechnet" and str(v.abgerechnet_rechnung_id) == rechnung["id"]
    (dose,) = await _verwendungen(*dose_v)
    assert dose.abrechnungsstatus == "offen" and dose.abgerechnet_rechnung_id is None
    # Die Sperre bucht keinen Bestand
    assert await _bestand_stand(kabel_id) == bestand_vorher

    vorschlaege = await client.get(
        f"/api/rechnungen/{rechnung['id']}/vorgaenge/{va.id}/vorschlaege", headers=auth_headers(token)
    )
    assert [(v["quelle"], v["material_id"]) for v in vorschlaege.json()] == [("material", str(dose_id))]
    offen = await _abrechenbar(client, token, kunde)
    assert offen[str(va.id)]["material_offen"] == 1
    assert offen[str(va.id)]["stunden_ohne_svs"] == "0.00"


@pytest.mark.asyncio
async def test_vorgang_nur_mit_material_ist_abrechenbar(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1", verwendungen=2)
    await _material(mandant, va, admin, bezeichnung="Dose", menge="1", preis="1")
    offen = await _abrechenbar(client, token, kunde)
    assert set(offen) == {str(va.id)}
    assert offen[str(va.id)]["material_offen"] == 2

    await sammelrechnung(client, token, kunde, va)
    assert await _abrechenbar(client, token, kunde) == {}


@pytest.mark.asyncio
async def test_zweiter_vorgang_und_erneutes_hinzufuegen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    dose_id, _ = await _material(mandant, va, admin, bezeichnung="Dose", menge="1", preis="4.50")
    rechnung = await _rechnung_anlegen(client, token, kunde)

    r1 = await _uebernehmen(client, token, rechnung["id"], va, nur=lambda v: v["quelle"] == "zeit")
    assert r1.status_code == 200
    r2 = await _uebernehmen(client, token, rechnung["id"], vb)
    assert r2.status_code == 200
    body = r2.json()
    assert [v["id"] for v in body["vorgaenge"]] == [str(va.id), str(vb.id)]
    assert [v["vorgangsnummer"] for v in body["vorgaenge"]] == ["V-A", "V-B"]
    assert [p["position"] for p in body["positionen"]] == [1, 2, 3]

    # Vorgang A erneut: nur noch das offene Material
    r3 = await _uebernehmen(client, token, rechnung["id"], va)
    assert r3.status_code == 200
    body = r3.json()
    assert [p["position"] for p in body["positionen"]] == [1, 2, 3, 4]
    assert body["positionen"][-1]["quelle"] == "material"
    assert body["positionen"][-1]["material_id"] == str(dose_id)
    # Reihenfolge nach erster Positionsnummer, A bleibt vorn und wird nicht doppelt gelistet
    assert [v["id"] for v in body["vorgaenge"]] == [str(va.id), str(vb.id)]

    # Weitere Uebernahme ohne offene Reste legt nichts an
    r4 = await _uebernehmen(client, token, rechnung["id"], va)
    assert r4.status_code == 400  # keine Vorschlaege -> leere Auswahl


@pytest.mark.asyncio
async def test_material_position_entfernen_gibt_verwendungen_frei(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    kabel_id, kabel_v = await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1", verwendungen=2)
    rechnung = await sammelrechnung(client, token, kunde, va)
    (pos,) = rechnung["positionen"]

    resp = await client.delete(f"/api/rechnungen/{rechnung['id']}/positionen/{pos['id']}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["vorgaenge"] == []
    for v in await _verwendungen(*kabel_v):
        assert v.abrechnungsstatus == "offen" and v.abgerechnet_rechnung_id is None
    assert str(va.id) in await _abrechenbar(client, token, kunde)


@pytest.mark.asyncio
async def test_add_position_vorschlagsbox_sperrt_material(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    kabel_id, kabel_v = await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1")
    headers = auth_headers(token)
    rechnung = await _rechnung_anlegen(client, token, kunde, vorgang_id=str(va.id))

    resp = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=headers,
        json={"beschreibung": "Kabel", "menge": "5", "einheit": "Stk", "einzelpreis": "1", "quelle": "material", "material_id": str(kabel_id)},
    )
    assert resp.status_code == 200, resp.text
    pos = resp.json()["positionen"][0]
    assert pos["vorgang_id"] == str(va.id) and pos["material_id"] == str(kabel_id)
    (v,) = await _verwendungen(*kabel_v)
    assert v.abrechnungsstatus == "abgerechnet"

    # fremdes/unbekanntes Material -> 400
    resp = await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=headers,
        json={"beschreibung": "X", "quelle": "material", "material_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 400

    resp = await client.delete(f"/api/rechnungen/{rechnung['id']}/positionen/{pos['id']}", headers=headers)
    assert resp.status_code == 200
    (v,) = await _verwendungen(*kabel_v)
    assert v.abrechnungsstatus == "offen"


@pytest.mark.asyncio
async def test_loeschen_restore_purge_und_storno_fuer_material(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    _, v1 = await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1", verwendungen=2)
    op_token = await _loeschen_user_token(client, make_user, mandant)

    # Entwurf loeschen -> frei (Verweis bleibt), Wiederherstellen -> wieder gesperrt
    rechnung = await sammelrechnung(client, token, kunde, va)
    assert (await client.delete(f"/api/rechnungen/{rechnung['id']}", headers=headers)).status_code == 204
    for v in await _verwendungen(*v1):
        assert v.abrechnungsstatus == "offen" and str(v.abgerechnet_rechnung_id) == rechnung["id"]
    assert str(va.id) in await _abrechenbar(client, token, kunde)

    resp = await client.post(f"/api/papierkorb/rechnung/{rechnung['id']}/wiederherstellen", headers=auth_headers(op_token))
    assert resp.status_code in (200, 204), resp.text
    for v in await _verwendungen(*v1):
        assert v.abrechnungsstatus == "abgerechnet" and str(v.abgerechnet_rechnung_id) == rechnung["id"]
    assert await _abrechenbar(client, token, kunde) == {}

    # Loeschen + Purge -> Verweis geloest, Material offen
    await client.delete(f"/api/rechnungen/{rechnung['id']}", headers=headers)
    resp = await client.delete(f"/api/papierkorb/rechnung/{rechnung['id']}", headers=auth_headers(op_token))
    assert resp.status_code == 204, resp.text
    for v in await _verwendungen(*v1):
        assert v.abrechnungsstatus == "offen" and v.abgerechnet_rechnung_id is None

    # Storno: versendet -> Stornorechnung gibt Material frei, Verweis NULL
    rechnung = await sammelrechnung(client, token, kunde, va)
    resp = await client.patch(f"/api/rechnungen/{rechnung['id']}", headers=headers, json={"status": "versendet"})
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=headers)
    assert resp.status_code == 201, resp.text
    storno = resp.json()
    for v in await _verwendungen(*v1):
        assert v.abrechnungsstatus == "offen" and v.abgerechnet_rechnung_id is None
    assert all(p["material_id"] is None and p["quelle"] is None for p in storno["positionen"])
    assert [v["id"] for v in storno["vorgaenge"]] == [str(va.id)]


@pytest.mark.asyncio
async def test_restore_ueberspringt_zwischenzeitlich_neu_abgerechnetes_material(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    _, v1 = await _material(mandant, va, admin, bezeichnung="Kabel", menge="5", preis="1")
    alt = await sammelrechnung(client, token, kunde, va)
    await client.delete(f"/api/rechnungen/{alt['id']}", headers=auth_headers(token))
    neu = await sammelrechnung(client, token, kunde, va)

    op_token = await _loeschen_user_token(client, make_user, mandant)
    await client.post(f"/api/papierkorb/rechnung/{alt['id']}/wiederherstellen", headers=auth_headers(op_token))
    (v,) = await _verwendungen(*v1)
    assert v.abrechnungsstatus == "abgerechnet" and str(v.abgerechnet_rechnung_id) == neu["id"]


@pytest.mark.asyncio
async def test_fremde_rechnung_404_und_fremdes_material_bleibt_unberuehrt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    fremder_mandant = await make_mandant(name="Fremd")
    fremder_admin = await make_user(mandant=fremder_mandant, role="mandant_admin", password="pw-123456")
    fremder_kunde = await make_kunde(mandant=fremder_mandant)
    fremder_vorgang = await make_vorgang(mandant=fremder_mandant, kunde=fremder_kunde)
    _, fremd_v = await _material(fremder_mandant, fremder_vorgang, fremder_admin, bezeichnung="Fremd", menge="1", preis="1")
    fremde_rechnung = await sammelrechnung(
        client, await login(client, fremder_admin.email, "pw-123456"), fremder_kunde, fremder_vorgang
    )

    r = await client.post(
        f"/api/rechnungen/{fremde_rechnung['id']}/vorgaenge",
        headers=auth_headers(token),
        json={"vorgang_id": str(va.id), "auswahl": [{"quelle": "zeit"}]},
    )
    assert r.status_code == 404
    r = await client.get(
        f"/api/rechnungen/{fremde_rechnung['id']}/vorgaenge/{va.id}/vorschlaege", headers=auth_headers(token)
    )
    assert r.status_code == 404
    (v,) = await _verwendungen(*fremd_v)
    assert v.abrechnungsstatus == "abgerechnet"


@pytest.mark.asyncio
async def test_pdf_gruppierte_rechnung_mit_gedankenstrich(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, kunde, va, vb, token = await _setup(client, make_mandant, make_user, make_kunde, make_vorgang)
    headers = auth_headers(token)
    vc = await make_vorgang(mandant=mandant, kunde=kunde, titel="Dach – Ost Ω", vorgangsnummer="V-C")
    await _daten_zwei_vorgaenge(mandant, admin, va, vb)
    async with system_session() as session:
        await _zeit(session, mandant=mandant, vorgang=vc, techniker=admin, stunden=1)
    await _material(mandant, vc, admin, bezeichnung="Dose – groß", menge="1", preis="4.50")

    rechnung = await _rechnung_anlegen(client, token, kunde)
    # freie Position ohne Vorgang steht vor den Gruppen
    await client.post(
        f"/api/rechnungen/{rechnung['id']}/positionen",
        headers=headers,
        json={"beschreibung": "Anfahrt – pauschal", "einzelpreis": "10"},
    )
    for v in (va, vb, vc):
        resp = await _uebernehmen(client, token, rechnung["id"], v, stundensatz="50")
        assert resp.status_code == 200, resp.text

    pdf = await client.get(f"/api/rechnungen/{rechnung['id']}/pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")

    resp = await client.patch(f"/api/rechnungen/{rechnung['id']}", headers=headers, json={"status": "versendet"})
    assert resp.status_code == 200, resp.text
    storno = await client.post(f"/api/rechnungen/{rechnung['id']}/storno", headers=headers)
    assert storno.status_code == 201, storno.text
    pdf = await client.get(f"/api/rechnungen/{storno.json()['id']}/pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_pdf_tabelle_ohne_vorgang_unveraendert_und_gruppen_mit_zwischensumme():
    from datetime import datetime, timezone
    from uuid import uuid4

    from fpdf import FPDF

    from app.models.rechnung import RechnungPosition
    from app.services import pdf_service

    vid = uuid4()

    def pos(nr, vorgang_id, preis):
        return RechnungPosition(
            position=nr, beschreibung=f"P{nr} – x", menge=Decimal("2"), einheit="Std",
            einzelpreis=Decimal(preis), vorgang_id=vorgang_id,
        )

    ohne = [pos(1, None, "10"), pos(2, None, "5")]
    a, b = FPDF(), FPDF()
    for pdf in (a, b):
        pdf.add_page()
    assert pdf_service._positionen_tabelle(a, ohne) == pdf_service._rechnung_positionen_tabelle(b, ohne, {}) == Decimal("30")

    gemischt = [pos(1, vid, "10"), pos(2, None, "5"), pos(3, vid, "1")]
    pdf = FPDF()
    pdf.add_page()
    summe = pdf_service._rechnung_positionen_tabelle(pdf, gemischt, {vid: ("V-00051", "Dach – Ost")})
    assert summe == Decimal("32")
    assert bytes(pdf.output()).startswith(b"%PDF")
