from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_vorgang_kennzahlen(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    tech1 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="T1")
    tech2 = await make_user(mandant=mandant, role="techniker", password="pw-123456", name="T2")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)

    projekt = (
        await client.post("/api/projekte", headers=auth_headers(token), json={"name": "Rollout"})
    ).json()

    # Zwei offene Vorgaenge fuer T1, einer fuer T2, einer unzugewiesen.
    await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech1.id, status="in_arbeit")
    await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech1.id, status="neu")
    await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech2.id, status="geplant")
    await make_vorgang(mandant=mandant, kunde=kunde, status="neu")
    # Ein abgeschlossener Vorgang zaehlt nicht als offen.
    await make_vorgang(mandant=mandant, kunde=kunde, zugewiesener_user_id=tech1.id, status="abgeschlossen")

    jetzt = datetime.now(timezone.utc)
    im_projekt = await make_vorgang(
        mandant=mandant,
        kunde=kunde,
        projekt_id=projekt["id"],
        status="abgeschlossen",
        # created_at ist (anders als abgeschlossen_am) ohne explizites
        # timezone=True gemappt -- asyncpg lehnt hier ein tz-aware datetime
        # ab, siehe app/db/base.py:TimestampMixin.
        created_at=(jetzt - timedelta(days=4)).replace(tzinfo=None),
        abgeschlossen_am=jetzt,
    )
    assert im_projekt.status == "abgeschlossen"

    resp = await client.get("/api/statistik/vorgang-kennzahlen", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["offene_vorgaenge_gesamt"] == 4
    je_techniker = {e["techniker_id"]: e["anzahl_offen"] for e in body["offene_vorgaenge_je_techniker"]}
    assert je_techniker[str(tech1.id)] == 2
    assert je_techniker[str(tech2.id)] == 1

    gefiltert = await client.get(
        "/api/statistik/vorgang-kennzahlen",
        headers=auth_headers(token),
        params={"projekt_id": projekt["id"]},
    )
    gefiltert_body = gefiltert.json()
    assert gefiltert_body["offene_vorgaenge_gesamt"] == 0
    assert gefiltert_body["abgeschlossene_vorgaenge_zeitraum"] == 1
    assert gefiltert_body["durchschnittliche_durchlaufzeit_tage"] == pytest.approx(4.0, abs=0.1)
