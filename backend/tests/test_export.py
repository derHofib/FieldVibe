from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.session import system_session
from app.models.material import MaterialBestand
from app.models.zeiterfassung import Zeiterfassung
from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_export_vorgaenge_csv(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Café Sonnenschein")
    await make_vorgang(mandant=mandant, kunde=kunde, titel="Störung Beleuchtung")
    token = await login(client, admin.email, "pw-123456")

    resp = await client.get("/api/vorgaenge/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8-sig")
    assert "Vorgangsnummer" in text
    assert "Café Sonnenschein" in text
    assert "Störung Beleuchtung" in text


@pytest.mark.asyncio
async def test_export_vorgaenge_csv_folgt_vorgaenge_sehen_recht(
    client, make_mandant, make_user
):
    # Seit der Umstellung auf frei konfigurierbare Account-Typen (siehe
    # app/api/routes/vorgaenge.py:export_vorgaenge_csv) ist der CSV-Export
    # keine eigene, hart auf disponent/mandant_admin verdrahtete Ausnahme
    # mehr, sondern folgt derselben vorgaenge.sehen-Freigabe wie das normale
    # Anzeigen der Liste -- ein techniker-artiger Account-Typ, der Vorgaenge
    # ohnehin einsehen darf, darf sie also auch als CSV exportieren. Ein
    # mandant_admin kann diese Freigabe je Account-Typ jederzeit ueber die
    # Account-Verwaltung entziehen.
    mandant = await make_mandant()
    techniker = await make_user(mandant=mandant, role="techniker", password="pw-123456")
    token = await login(client, techniker.email, "pw-123456")

    resp = await client.get("/api/vorgaenge/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_export_zeiterfassung_csv(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    techniker = await make_user(mandant=mandant, role="techniker", name="Erika Musterfrau")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    start = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    async with system_session() as session:
        session.add(
            Zeiterfassung(
                mandant_id=mandant.id,
                vorgang_id=vorgang.id,
                techniker_id=techniker.id,
                start_at=start,
                ende_at=start + timedelta(hours=2),
                taetigkeit="Fehlersuche",
            )
        )
        await session.flush()

    token = await login(client, admin.email, "pw-123456")
    resp = await client.get("/api/zeiterfassung/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    assert "Erika Musterfrau" in text
    assert "Fehlersuche" in text
    assert "2,00" in text


@pytest.mark.asyncio
async def test_export_material_csv(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    create_resp = await client.post(
        "/api/material",
        headers=auth_headers(token),
        json={"bezeichnung": "Sicherung 16A", "einheit": "Stk", "menge": "20", "mindestbestand": "5"},
    )
    assert create_resp.status_code == 201

    resp = await client.get("/api/material/export/csv", headers=auth_headers(token))
    assert resp.status_code == 200
    text = resp.content.decode("utf-8-sig")
    assert "Sicherung 16A" in text
    assert "Zentrallager" in text
    assert "20" in text
