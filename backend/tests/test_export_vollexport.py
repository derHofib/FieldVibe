"""Mandanten-Vollexport: asynchron, ZIP-Inhalt, Manifest-Hashes, Mandantentrennung, Secrets."""
import asyncio
import hashlib
import io
import json
import uuid
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select, text, update

from app.db.session import system_session
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.mandant import Mandant
from app.models.mandant_export import MandantExport
from app.models.rechnung import Rechnung
from app.models.vorgang_event import VorgangEvent
from app.services import audit_service, export_job_service, storage_service, vollexport_service
from tests.conftest import auth_headers, login


async def _fertig_abwarten() -> None:
    tasks = export_job_service.hintergrund_tasks()
    if tasks:
        await asyncio.gather(*tasks)


async def _betrieb(client, make_mandant, make_user, make_kunde, *, name: str, kundenname: str):
    mandant = await make_mandant(name)
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456", name=f"Admin {name}")
    kunde = await make_kunde(mandant=mandant, name=kundenname)
    token = await login(client, admin.email, "pw-123456")
    return mandant, admin, kunde, auth_headers(token)


async def _rechnung_versenden(client, h, kunde) -> str:
    r = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "100"})).json()
    assert (await client.patch(f"/api/rechnungen/{r['id']}", headers=h, json={"status": "versendet"})).status_code == 200
    return r["rechnungsnummer"]


async def _zip_holen(client, h, export_id: str) -> tuple[zipfile.ZipFile, bytes]:
    dl = await client.get(f"/api/exporte/{export_id}/download-url", headers=h)
    assert dl.status_code == 200, dl.text
    async with httpx.AsyncClient() as http:
        antwort = await http.get(dl.json()["url"])
    assert antwort.status_code == 200
    return zipfile.ZipFile(io.BytesIO(antwort.content)), antwort.content


@pytest.mark.asyncio
async def test_vollexport_ablauf_inhalt_manifest_und_mandantentrennung(client, make_mandant, make_user, make_kunde):
    a, admin_a, kunde_a, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Alpha", kundenname="Alpha-Kunde GmbH")
    b, admin_b, kunde_b, hb = await _betrieb(client, make_mandant, make_user, make_kunde, name="Beta", kundenname="GEHEIM-B-KUNDE AG")
    nummer_a = await _rechnung_versenden(client, h, kunde_a)
    await _rechnung_versenden(client, hb, kunde_b)

    # Foto/Dokument-Ereignis mit Objekt (Mandant A) und eins von B; Eingangsbeleg von A.
    async with system_session() as session:
        from app.models.vorgang import Vorgang

        v_a = Vorgang(mandant_id=a.id, vorgangsnummer="V-A1", kunde_id=kunde_a.id, titel="Alpha-Vorgang", abrechnungsart="aufwand", leistungstyp="stoerung")
        v_b = Vorgang(mandant_id=b.id, vorgangsnummer="V-B1", kunde_id=kunde_b.id, titel="GEHEIM-B-VORGANG", abrechnungsart="aufwand", leistungstyp="stoerung")
        session.add_all([v_a, v_b])
        await session.flush()
        key_a = storage_service.new_object_key(a.id, v_a.id, "foto.jpg")
        key_b = storage_service.new_object_key(b.id, v_b.id, "foto.jpg")
        await storage_service.upload_bytes(key_a, b"FOTO-ALPHA" * 1000, "image/jpeg")
        await storage_service.upload_bytes(key_b, b"FOTO-GEHEIM-B", "image/jpeg")
        session.add(VorgangEvent(mandant_id=a.id, vorgang_id=v_a.id, event_type="foto", payload={"key": key_a, "thumbnail_key": key_a + "_t"}))
        session.add(VorgangEvent(mandant_id=b.id, vorgang_id=v_b.id, event_type="foto", payload={"key": key_b}))
        beleg_key = storage_service.new_eingangsrechnung_beleg_key(a.id, uuid.uuid4(), "beleg.pdf")
        await storage_service.upload_bytes(beleg_key, b"%PDF-EINGANG", "application/pdf")
        session.add(
            Eingangsrechnung(
                mandant_id=a.id, lieferant_name="Alpha-Lieferant", rechnungsnummer_lieferant="L-1",
                rechnungsdatum=date(2026, 1, 5), betrag_netto=Decimal("10"), beleg_object_key=beleg_key, status="offen",
            )
        )
        # Einstellungen mit Geheimnis-Schluessel: darf nur maskiert exportiert werden.
        mandant = await session.get(Mandant, a.id)
        mandant.firmendaten = {**mandant.firmendaten, "ust_idnr": "DE123456789", "smtp_passwort": "streng-geheim"}
        user_hash = (await session.execute(text("SELECT password_hash FROM users WHERE id = :i"), {"i": admin_a.id})).scalar_one()

    resp = await client.post("/api/exporte/vollexport", headers=h)
    assert resp.status_code == 202
    export_id = resp.json()["id"]
    await _fertig_abwarten()

    status_ = (await client.get(f"/api/exporte/{export_id}", headers=h)).json()
    assert status_["status"] == "fertig", status_
    assert status_["laeuft_ab_am"] is not None
    jetzt = datetime.now(timezone.utc)
    ab = datetime.fromisoformat(status_["laeuft_ab_am"])
    assert timedelta(days=6, hours=23) < ab - jetzt < timedelta(days=7, hours=1)

    archiv, rohdaten = await _zip_holen(client, h, export_id)
    assert hashlib.sha256(rohdaten).hexdigest() == status_["sha256"]
    namen = set(archiv.namelist())
    for erwartet in ("manifest.json", "README.txt", "einstellungen.json", "daten/kunden.csv", "daten/kunden.json",
                     "daten/rechnungen.csv", "daten/rechnung_positionen.json", "daten/nutzer.csv", "daten/protokoll.csv",
                     f"belege/rechnungen/{nummer_a}.pdf"):
        assert erwartet in namen, erwartet
    assert any(n.startswith("dokumente/vorgaenge/") for n in namen)
    assert any(n.startswith("belege/eingangsrechnungen/") for n in namen)

    # Manifest: je Datei Groesse und SHA-256 stimmen mit dem tatsaechlichen Inhalt ueberein.
    manifest = json.loads(archiv.read("manifest.json"))
    assert manifest["art"] == "vollexport" and manifest["mandant"]["id"] == str(a.id)
    pfade = set()
    for eintrag in manifest["dateien"]:
        inhalt = archiv.read(eintrag["pfad"])
        assert hashlib.sha256(inhalt).hexdigest() == eintrag["sha256"], eintrag["pfad"]
        assert len(inhalt) == eintrag["groesse_bytes"]
        pfade.add(eintrag["pfad"])
    assert pfade == namen - {"manifest.json"}
    assert manifest["protokoll_kettenkopf"]["kette_ok"] is True

    # Inhalte: eigene Daten da, JSON/CSV konsistent, Belegbytes entsprechen dem Archiv.
    kunden = json.loads(archiv.read("daten/kunden.json"))
    assert [k["name"] for k in kunden] == ["Alpha-Kunde GmbH"]
    assert "Alpha-Kunde GmbH" in archiv.read("daten/kunden.csv").decode("utf-8-sig")
    foto = next(n for n in namen if n.startswith("dokumente/vorgaenge/"))
    assert archiv.read(foto) == b"FOTO-ALPHA" * 1000

    # Mandantentrennung: nichts von Betrieb B irgendwo im ZIP (Namen, Nummern, Objekte, IDs).
    for name in archiv.namelist():
        daten = archiv.read(name)
        assert b"GEHEIM-B" not in daten, name
        assert str(b.id).encode() not in daten, name
        assert str(kunde_b.id).encode() not in daten, name

    # Secrets: weder Passwort-Hash noch MFA-/Token-Felder noch Geheimnisse aus den Einstellungen.
    alles = b"".join(archiv.read(n) for n in namen if n.endswith((".csv", ".json", ".txt")))
    assert user_hash.encode() not in alles
    for verboten in (b"password_hash", b"mfa_secret", b"mfa_wiederherstellung", b"token_version", b"streng-geheim"):
        assert verboten not in alles, verboten
    einstellungen = json.loads(archiv.read("einstellungen.json"))
    assert einstellungen["firmendaten"]["smtp_passwort"] == "***"
    assert einstellungen["firmendaten"]["ust_idnr"] == "DE123456789"
    nutzer = json.loads(archiv.read("daten/nutzer.json"))
    assert set(nutzer[0]) == {"id", "mandant_id", "email", "name", "role", "account_typ_id", "aktiv", "mfa_aktiv", "created_at", "updated_at"}

    # Auditspur: angefordert, fertig, Download; Kette bleibt gueltig.
    liste = (await client.get("/api/audit", params={"aktion": "export_vollexport", "limit": 50}, headers=h)).json()
    aktionen = {e["aktion"] for e in liste["eintraege"]}
    assert {"export_vollexport_angefordert", "export_vollexport_fertig", "export_vollexport_download"} <= aktionen
    assert (await client.get("/api/audit/verifizieren", headers=h)).json()["ok"] is True

    # Betrieb B sieht den Export von A nicht.
    assert (await client.get(f"/api/exporte/{export_id}", headers=hb)).status_code == 404
    assert (await client.get(f"/api/exporte/{export_id}/download-url", headers=hb)).status_code == 404
    assert (await client.get("/api/exporte", headers=hb)).json() == []


@pytest.mark.asyncio
async def test_nur_mandant_admin_und_ein_laufender_export_je_mandant(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant, admin, _, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Gamma", kundenname="K")
    for rolle in ("techniker", "loesch_operativ", "loesch_ansicht"):
        u = await make_user(mandant=mandant, role=rolle, password="pw-123456")
        uh = auth_headers(await login(client, u.email, "pw-123456"))
        assert (await client.post("/api/exporte/vollexport", headers=uh)).status_code == 403, rolle
        assert (await client.get("/api/exporte", headers=uh)).status_code == 403, rolle
    assert (await client.post("/api/exporte/vollexport")).status_code == 401

    async def nichts():
        return None

    monkeypatch.setattr(export_job_service, "_hintergrund", nichts)
    erster = await client.post("/api/exporte/vollexport", headers=h)
    assert erster.status_code == 202 and erster.json()["status"] == "wartend"
    zweiter = await client.post("/api/exporte/vollexport", headers=h)
    assert zweiter.status_code == 409
    # Auch ein Z3-Auftrag zaehlt als laufender Export.
    assert (await client.post("/api/exporte/z3", headers=h, json={"von": "2026-01-01", "bis": "2026-12-31"})).status_code == 409
    # Anderer Betrieb ist nicht betroffen.
    _, _, _, h2 = await _betrieb(client, make_mandant, make_user, make_kunde, name="Delta", kundenname="K2")
    assert (await client.post("/api/exporte/vollexport", headers=h2)).status_code == 202

    # Download vor Fertigstellung nicht moeglich.
    assert (await client.get(f"/api/exporte/{erster.json()['id']}/download-url", headers=h)).status_code == 409
    # Verarbeitung durch den Worker-Pfad; danach ist ein neuer Export erlaubt.
    while await export_job_service.verarbeite_naechsten() is not None:
        pass
    assert (await client.get(f"/api/exporte/{erster.json()['id']}", headers=h)).json()["status"] == "fertig"
    assert (await client.post("/api/exporte/vollexport", headers=h)).status_code == 202


@pytest.mark.asyncio
async def test_ergebnis_wird_nach_sieben_tagen_entfernt(client, make_mandant, make_user, make_kunde):
    mandant, _, _, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Eps", kundenname="K")
    export_id = (await client.post("/api/exporte/vollexport", headers=h)).json()["id"]
    await _fertig_abwarten()
    async with system_session() as session:
        job = await session.get(MandantExport, uuid.UUID(export_id))
        key = job.object_key
        assert key.startswith(f"mandanten/{mandant.id}/exporte/")
        storage_service._internal_client.head_object(Bucket=storage_service.BUCKET, Key=key)
        job.laeuft_ab_am = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert await export_job_service.raeume_auf() == 1
    with pytest.raises(ClientError):
        storage_service._internal_client.head_object(Bucket=storage_service.BUCKET, Key=key)
    nach = (await client.get(f"/api/exporte/{export_id}", headers=h)).json()
    assert nach["status"] == "abgelaufen"
    assert (await client.get(f"/api/exporte/{export_id}/download-url", headers=h)).status_code == 409
    # Erneutes Aufraeumen ist ein No-op; ein neuer Export ist moeglich.
    assert await export_job_service.raeume_auf() == 0
    assert (await client.post("/api/exporte/vollexport", headers=h)).status_code == 202


@pytest.mark.asyncio
async def test_fehlgeschlagener_export_wird_protokolliert_und_blockiert_nicht(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant, _, _, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Zeta", kundenname="K")

    async def kaputt(*args, **kwargs):
        raise RuntimeError("Speicher voll")

    monkeypatch.setattr(vollexport_service, "erzeuge", kaputt)
    export_id = (await client.post("/api/exporte/vollexport", headers=h)).json()["id"]
    await _fertig_abwarten()
    job = (await client.get(f"/api/exporte/{export_id}", headers=h)).json()
    assert job["status"] == "fehler" and "Speicher voll" in job["fehler"]
    monkeypatch.undo()
    assert (await client.post("/api/exporte/vollexport", headers=h)).status_code == 202
    aktionen = {e["aktion"] for e in (await client.get("/api/audit", params={"aktion": "export_vollexport_fehl"}, headers=h)).json()["eintraege"]}
    assert aktionen == {"export_vollexport_fehlgeschlagen"}


@pytest.mark.asyncio
async def test_haengender_auftrag_wird_als_fehler_markiert(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant, admin, _, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Eta", kundenname="K")
    async with system_session() as session:
        session.add(
            MandantExport(
                mandant_id=mandant.id, art="vollexport", status="laeuft", angefordert_von=admin.id,
                gestartet_am=datetime.now(timezone.utc) - timedelta(hours=3),
            )
        )
    assert await export_job_service.verarbeite_naechsten() is None
    async with system_session() as session:
        job = (await session.execute(select(MandantExport))).scalar_one()
        assert job.status == "fehler" and "Zeitüberschreitung" in job.fehler
    assert (await client.post("/api/exporte/vollexport", headers=h)).status_code == 202


@pytest.mark.asyncio
async def test_fremder_objektschluessel_gelangt_nie_in_den_export(client, make_mandant, make_user, make_kunde):
    a, _, kunde_a, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Theta", kundenname="K")
    b = await make_mandant("Fremd")
    fremder_key = storage_service.new_object_key(b.id, uuid.uuid4(), "foto.jpg")
    await storage_service.upload_bytes(fremder_key, b"GEHEIMES-FREMDFOTO", "image/jpeg")
    async with system_session() as session:
        from app.models.vorgang import Vorgang

        v = Vorgang(mandant_id=a.id, vorgangsnummer="V-T1", kunde_id=kunde_a.id, titel="T", abrechnungsart="aufwand", leistungstyp="stoerung")
        session.add(v)
        await session.flush()
        # Falsch gesetzter Verweis (Fehler/Manipulation): zeigt auf ein Objekt des anderen Betriebs.
        session.add(VorgangEvent(mandant_id=a.id, vorgang_id=v.id, event_type="foto", payload={"key": fremder_key}))
    export_id = (await client.post("/api/exporte/vollexport", headers=h)).json()["id"]
    await _fertig_abwarten()
    archiv, _ = await _zip_holen(client, h, export_id)
    assert not any(n.startswith("dokumente/vorgaenge/") for n in archiv.namelist())
    manifest = json.loads(archiv.read("manifest.json"))
    assert any("gehoert nicht zu diesem Betrieb" in u["grund"] for u in manifest["uebersprungen"])
    assert all(b"GEHEIMES-FREMDFOTO" not in archiv.read(n) for n in archiv.namelist())


@pytest.mark.asyncio
async def test_grosses_objekt_wird_gestreamt_und_stimmt_im_hash(client, make_mandant, make_user, make_kunde):
    a, _, kunde_a, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Iota", kundenname="K")
    gross = (b"0123456789abcdef" * 65536) * 5  # 5 MiB
    async with system_session() as session:
        from app.models.vorgang import Vorgang

        v = Vorgang(mandant_id=a.id, vorgangsnummer="V-I1", kunde_id=kunde_a.id, titel="T", abrechnungsart="aufwand", leistungstyp="stoerung")
        session.add(v)
        await session.flush()
        key = storage_service.new_object_key(a.id, v.id, "plan.pdf")
        await storage_service.upload_bytes(key, gross, "application/pdf")
        session.add(VorgangEvent(mandant_id=a.id, vorgang_id=v.id, event_type="dokument", payload={"key": key, "dateiname": "plan.pdf"}))
    export_id = (await client.post("/api/exporte/vollexport", headers=h)).json()["id"]
    await _fertig_abwarten()
    archiv, _ = await _zip_holen(client, h, export_id)
    manifest = json.loads(archiv.read("manifest.json"))
    eintrag = next(d for d in manifest["dateien"] if d["pfad"].endswith("_plan.pdf"))
    assert eintrag["groesse_bytes"] == len(gross)
    assert eintrag["sha256"] == hashlib.sha256(gross).hexdigest()


@pytest.mark.asyncio
async def test_csv_im_export_ist_gegen_formelinjektion_geschuetzt(client, make_mandant, make_user, make_kunde):
    a, _, _, h = await _betrieb(client, make_mandant, make_user, make_kunde, name="Kappa", kundenname="=HYPERLINK(\"http://boese.example\")")
    export_id = (await client.post("/api/exporte/vollexport", headers=h)).json()["id"]
    await _fertig_abwarten()
    archiv, _ = await _zip_holen(client, h, export_id)
    csv_text = archiv.read("daten/kunden.csv").decode("utf-8-sig")
    assert "'=HYPERLINK" in csv_text and ";=HYPERLINK" not in csv_text
    # Das JSON behaelt den Originalwert (maschinenlesbar, keine Excel-Auswertung).
    assert json.loads(archiv.read("daten/kunden.json"))[0]["name"].startswith("=HYPERLINK")
