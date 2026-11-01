"""DB-seitige Festschreibung versendeter Rechnungen und SHA-256 der Archivobjekte."""
import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError

from app.db.session import system_session
from app.models.material import Material
from app.models.rechnung import Rechnung, RechnungPosition
from app.services import storage_service
from tests.conftest import auth_headers, login


async def _versendete_rechnung(client, make_mandant, make_user, make_kunde, *, positionen=None):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    token = await login(client, admin.email, "pw-123456")
    h = auth_headers(token)
    body = {"kunde_id": str(kunde.id), "betrag_netto": "100"}
    if positionen:
        body = {"kunde_id": str(kunde.id), "positionen": positionen}
    created = await client.post("/api/rechnungen", headers=h, json=body)
    assert created.status_code == 201, created.text
    rechnung_id = created.json()["id"]
    sent = await client.patch(f"/api/rechnungen/{rechnung_id}", headers=h, json={"status": "versendet"})
    assert sent.status_code == 200, sent.text
    return mandant, kunde, h, rechnung_id


async def _sql(sql: str, **params):
    async with system_session() as session:
        await session.execute(text(sql), params)


@pytest.mark.asyncio
async def test_entwurf_bleibt_frei_aenderbar(client, make_mandant, make_user, make_kunde):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    h = auth_headers(await login(client, admin.email, "pw-123456"))
    r = (await client.post("/api/rechnungen", headers=h, json={"kunde_id": str(kunde.id), "betrag_netto": "100"})).json()
    await _sql("UPDATE rechnungen SET betrag_netto = 5, rechnungsnummer = 'X-1' WHERE id = :i", i=r["id"])
    await _sql("DELETE FROM rechnungen WHERE id = :i", i=r["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setzung",
    [
        "betrag_netto = 1",
        "mwst_satz = 7",
        "rechnungsnummer = 'FAELSCHUNG'",
        "faellig_am = '2030-01-01'",
        "leistungsdatum = '2030-01-01'",
        "versendet_am = now() - interval '5 days'",
        "ist_storno = true",
        "rechnungsart = 'gutschrift'",
        "gutschrift_grund = 'x'",
        "kunde_id = gen_random_uuid()",
        "status = 'entwurf'",
    ],
)
async def test_kernfelder_versendeter_rechnung_sind_unveraenderbar(
    client, make_mandant, make_user, make_kunde, setzung
):
    _, _, _, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    with pytest.raises(DBAPIError, match="festgeschrieben"):
        await _sql(f"UPDATE rechnungen SET {setzung} WHERE id = :i", i=rechnung_id)


@pytest.mark.asyncio
async def test_erlaubte_updates_nach_versand(client, make_mandant, make_user, make_kunde):
    _, _, _, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    # Status-Uebergaenge, Zahlungs- und Mahnfelder, Papierkorb-Markierung.
    await _sql("UPDATE rechnungen SET status = 'teilweise_bezahlt' WHERE id = :i", i=rechnung_id)
    await _sql("UPDATE rechnungen SET status = 'bezahlt', bezahlt_am = now() WHERE id = :i", i=rechnung_id)
    await _sql("UPDATE rechnungen SET status = 'versendet', bezahlt_am = NULL WHERE id = :i", i=rechnung_id)
    await _sql("UPDATE rechnungen SET mahnstufe = 2, letzte_mahnung_am = now() WHERE id = :i", i=rechnung_id)
    await _sql("UPDATE rechnungen SET geloescht_am = now() WHERE id = :i", i=rechnung_id)
    await _sql("UPDATE rechnungen SET status = 'storniert' WHERE id = :i", i=rechnung_id)


@pytest.mark.asyncio
async def test_archivangaben_sind_einmal_beschreibbar(client, make_mandant, make_user, make_kunde):
    _, _, _, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    for spalte in ("pdf_object_key", "pdf_sha256"):
        with pytest.raises(DBAPIError, match="Archivangaben"):
            await _sql(
                f"UPDATE rechnungen SET {spalte} = :w WHERE id = :i",
                w="a" * 64 if spalte.endswith("sha256") else "anderer/key.pdf",
                i=rechnung_id,
            )
    # NULL -> Wert: ein Rechnungs-Archiv ohne XML darf die XML-Angaben spaeter einmalig erhalten.
    await _sql("UPDATE rechnungen SET xml_object_key = 'k.xml', xml_sha256 = :h WHERE id = :i", h="b" * 64, i=rechnung_id)
    with pytest.raises(DBAPIError, match="Archivangaben"):
        await _sql("UPDATE rechnungen SET xml_sha256 = :h WHERE id = :i", h="c" * 64, i=rechnung_id)


@pytest.mark.asyncio
async def test_positionen_versendeter_rechnung_sind_unveraenderbar(client, make_mandant, make_user, make_kunde):
    _, _, _, rechnung_id = await _versendete_rechnung(
        client,
        make_mandant,
        make_user,
        make_kunde,
        positionen=[{"beschreibung": "Arbeit", "menge": "2", "einheit": "Std", "einzelpreis": "50.00"}],
    )
    for sql in (
        "UPDATE rechnung_positionen SET einzelpreis = 1 WHERE rechnung_id = :i",
        "UPDATE rechnung_positionen SET beschreibung = 'x' WHERE rechnung_id = :i",
        "UPDATE rechnung_positionen SET steuer_satz = 7, steuer_kategorie = 'S' WHERE rechnung_id = :i",
        "DELETE FROM rechnung_positionen WHERE rechnung_id = :i",
    ):
        with pytest.raises(DBAPIError, match="festgeschriebenen Rechnung"):
            await _sql(sql, i=rechnung_id)


@pytest.mark.asyncio
async def test_rechnung_loeschen_nur_mit_freigabe(client, make_mandant, make_user, make_kunde):
    _, _, _, rechnung_id = await _versendete_rechnung(
        client,
        make_mandant,
        make_user,
        make_kunde,
        positionen=[{"beschreibung": "Arbeit", "menge": "1", "einheit": "Std", "einzelpreis": "50.00"}],
    )
    with pytest.raises(DBAPIError, match="nicht geloescht werden"):
        await _sql("DELETE FROM rechnungen WHERE id = :i", i=rechnung_id)

    # Freigabe (setzt papierkorb_service.purge nach der Fristpruefung): Kaskade auf die Positionen.
    async with system_session() as session:
        await session.execute(text("SELECT set_config('app.gobd_loeschfreigabe', 'true', true)"))
        await session.execute(delete(Rechnung).where(Rechnung.id == rechnung_id))
    async with system_session() as session:
        assert await session.get(Rechnung, rechnung_id) is None
        assert (await session.execute(select(RechnungPosition))).first() is None


@pytest.mark.asyncio
async def test_belege_duerfen_in_derselben_transaktion_fertig_befuellt_werden(make_mandant, make_user, make_kunde):
    """Storno-/Gutschriftsbelege entstehen als versendet und bekommen danach noch Betrag und Positionen."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant)
    async with system_session() as session:
        r = Rechnung(
            mandant_id=mandant.id,
            kunde_id=kunde.id,
            rechnungsnummer="R-TX-1",
            betrag_netto=Decimal("0"),
            mwst_satz=Decimal("19"),
            status="versendet",
            versendet_am=datetime.now(timezone.utc),
            erstellt_von=admin.id,
        )
        session.add(r)
        await session.flush()
        r.betrag_netto = Decimal("-10")
        session.add(
            RechnungPosition(
                mandant_id=mandant.id,
                rechnung_id=r.id,
                position=1,
                beschreibung="Gegenbuchung",
                menge=Decimal("1"),
                einheit="Stk",
                einzelpreis=Decimal("-10"),
            )
        )
        await session.flush()
        rechnung_id = r.id
    # Eine Transaktion spaeter ist alles festgeschrieben.
    with pytest.raises(DBAPIError, match="festgeschrieben"):
        await _sql("UPDATE rechnungen SET betrag_netto = -1 WHERE id = :i", i=rechnung_id)


@pytest.mark.asyncio
async def test_aufloesen_von_verweisen_bleibt_erlaubt(client, make_mandant, make_user, make_kunde):
    """FK ... ON DELETE SET NULL (Material) aendert eine Position einer versendeten Rechnung -- das
    ist ein Verweis, kein Inhalt, und darf das Loeschen des Materials nicht blockieren."""
    mandant, kunde, h, rechnung_id = await _versendete_rechnung(
        client,
        make_mandant,
        make_user,
        make_kunde,
        positionen=[{"beschreibung": "Kabel", "menge": "1", "einheit": "m", "einzelpreis": "2.00"}],
    )
    async with system_session() as session:
        material = Material(mandant_id=mandant.id, bezeichnung="Kabel", einheit="m", einzelpreis=Decimal("2"))
        session.add(material)
        await session.flush()
        material_id = material.id
    # Verweis setzen geht nicht (nur Aufloesen ist erlaubt) ...
    with pytest.raises(DBAPIError, match="festgeschriebenen Rechnung"):
        await _sql("UPDATE rechnung_positionen SET material_id = :m WHERE rechnung_id = :i", m=material_id, i=rechnung_id)
    # ... wohl aber das Aufloesen eines vorhandenen: Position in derselben Transaktion anlegen und
    # das Material danach loeschen.
    async with system_session() as session:
        pos = (await session.execute(select(RechnungPosition).where(RechnungPosition.rechnung_id == rechnung_id))).scalar_one()
        await session.execute(text("ALTER TABLE rechnung_positionen DISABLE TRIGGER trg_rechnung_positionen_festschreibung"))
        await session.execute(
            update(RechnungPosition).where(RechnungPosition.id == pos.id).values(material_id=material_id)
        )
        await session.execute(text("ALTER TABLE rechnung_positionen ENABLE TRIGGER trg_rechnung_positionen_festschreibung"))
    async with system_session() as session:
        await session.execute(delete(Material).where(Material.id == material_id))
        pos = (await session.execute(select(RechnungPosition).where(RechnungPosition.rechnung_id == rechnung_id))).scalar_one()
        assert pos.material_id is None


@pytest.mark.asyncio
async def test_versand_speichert_sha256_des_archivierten_pdf(client, make_mandant, make_user, make_kunde):
    _, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    async with system_session() as session:
        r = await session.get(Rechnung, rechnung_id)
        inhalt = await storage_service.download_bytes(r.pdf_object_key)
        assert r.pdf_sha256 == hashlib.sha256(inhalt).hexdigest()
        assert r.xml_sha256 is None and r.xml_object_key is None


@pytest.mark.asyncio
async def test_archivpruefung_erkennt_veraendertes_und_fehlendes_objekt(client, make_mandant, make_user, make_kunde):
    _, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    ok = (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=h)).json()
    assert ok["ok"] is True
    assert ok["objekte"][0]["art"] == "pdf" and ok["objekte"][0]["status"] == "ok"

    async with system_session() as session:
        key = (await session.get(Rechnung, rechnung_id)).pdf_object_key
    await storage_service.upload_bytes(key, b"%PDF-manipuliert", "application/pdf")
    abw = (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=h)).json()
    assert abw["ok"] is False and abw["objekte"][0]["status"] == "abweichung"
    assert abw["objekte"][0]["hash_gespeichert"] != abw["objekte"][0]["hash_berechnet"]

    await storage_service.delete_object(key)
    fehlt = (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=h)).json()
    assert fehlt["objekte"][0]["status"] == "fehlt"

    audit = (await client.get("/api/audit", params={"aktion": "archiv_abweichung"}, headers=h)).json()
    assert audit["gesamt"] == 2


@pytest.mark.asyncio
async def test_hash_nachtragen_fuer_altbestand(client, make_mandant, make_user, make_kunde):
    _, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    # Altbestand simulieren: Hash fehlt (Trigger kurz aus, wie es nur ein Betreiber koennte).
    async with system_session() as session:
        await session.execute(text("ALTER TABLE rechnungen DISABLE TRIGGER trg_rechnungen_festschreibung"))
        await session.execute(update(Rechnung).where(Rechnung.id == rechnung_id).values(pdf_sha256=None))
        await session.execute(text("ALTER TABLE rechnungen ENABLE TRIGGER trg_rechnungen_festschreibung"))
    vorher = (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=h)).json()
    assert vorher["objekte"][0]["status"] == "kein_hash" and vorher["ok"] is False

    nachher = (await client.post(f"/api/rechnungen/{rechnung_id}/archiv-pruefung/hash-nachtragen", headers=h)).json()
    assert nachher["ok"] is True
    # Wiederholung aendert nichts mehr (kein Hash zu ergaenzen, kein zweiter Audit-Eintrag).
    await client.post(f"/api/rechnungen/{rechnung_id}/archiv-pruefung/hash-nachtragen", headers=h)
    audit = (await client.get("/api/audit", params={"aktion": "archiv_hash_nachgetragen"}, headers=h)).json()
    assert audit["gesamt"] == 1


@pytest.mark.asyncio
async def test_archivpruefung_nur_fuer_mandant_admin(client, make_mandant, make_user, make_kunde):
    mandant, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    th = auth_headers(await login(client, techniker.email, "pw-123456"))
    assert (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=th)).status_code == 403
    fremd = await make_mandant("Fremd")
    fremd_admin = await make_user(mandant=fremd, role="mandant_admin", password="pw-123456")
    fh = auth_headers(await login(client, fremd_admin.email, "pw-123456"))
    assert (await client.get(f"/api/rechnungen/{rechnung_id}/archiv-pruefung", headers=fh)).status_code == 404


@pytest.mark.asyncio
async def test_object_lock_retention_bis_fristende_wenn_aktiviert(client, make_mandant, make_user, make_kunde, monkeypatch):
    """Optionales WORM: nur mit Object-Lock-Bucket und S3_RECHNUNGEN_RETENTION. Gegen moto geprueft,
    NICHT gegen echtes MinIO."""
    from botocore.exceptions import ClientError

    bucket = "fieldvibe-lock-test"
    storage_service._internal_client.create_bucket(Bucket=bucket, ObjectLockEnabledForBucket=True)
    monkeypatch.setattr(storage_service, "BUCKET", bucket)
    monkeypatch.setattr(storage_service._settings, "s3_rechnungen_retention", "governance")

    _, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    async with system_session() as session:
        key = (await session.get(Rechnung, rechnung_id)).pdf_object_key
    kopf = storage_service._internal_client.head_object(Bucket=bucket, Key=key)
    assert kopf["ObjectLockMode"] == "GOVERNANCE"
    erwartet_jahr = date.today().year + 8 + 1  # Fristende 31.12.(Jahr+8), Retention bis zum Folgetag
    assert kopf["ObjectLockRetainUntilDate"].year == erwartet_jahr
    with pytest.raises(ClientError):
        storage_service._internal_client.delete_object(Bucket=bucket, Key=key, VersionId=kopf["VersionId"])


@pytest.mark.asyncio
async def test_ohne_retention_einstellung_bleibt_upload_unveraendert(client, make_mandant, make_user, make_kunde):
    _, _, h, rechnung_id = await _versendete_rechnung(client, make_mandant, make_user, make_kunde)
    async with system_session() as session:
        key = (await session.get(Rechnung, rechnung_id)).pdf_object_key
    kopf = storage_service._internal_client.head_object(Bucket=storage_service.BUCKET, Key=key)
    assert "ObjectLockMode" not in kopf
