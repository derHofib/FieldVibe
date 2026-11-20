"""erstellt_via (Migration 0129): 'ki' bei Anlage ueber ein MCP-Token (via=mcp), 'app' bei normalem Login."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import create_access_token
from tests.conftest import auth_headers, login


def _mcp_token(user) -> str:
    return create_access_token(
        subject=user.id,
        role=user.role,
        mandant_id=user.mandant_id,
        token_version=user.token_version,
        account_typ_id=user.account_typ_id,
        via="mcp",
        ki_verbindung_id=uuid.uuid4(),
        expires_delta=timedelta(minutes=2),
    )


async def _anlegen(client, headers, techniker, vorgang_id, kunde_id) -> dict[str, dict]:
    """Legt je einen Datensatz der sechs Tabellen an und liefert die Antworten."""
    start = datetime.now(timezone.utc) + timedelta(days=1)
    anfragen = {
        "vorgang": ("/api/vorgaenge", {"kunde_id": str(kunde_id), "titel": "T", "leistungstyp": "wartung", "abrechnungsart": "aufwand"}),
        "auftrag": ("/api/auftraege", {"titel": "A"}),
        "projekt": ("/api/projekte", {"name": "P"}),
        "angebot": ("/api/angebote", {"kunde_id": str(kunde_id), "positionen": [{"beschreibung": "x", "menge": "1", "einheit": "Std", "einzelpreis": "10"}]}),
        "rechnung": ("/api/rechnungen", {"kunde_id": str(kunde_id), "betrag_netto": "10.00"}),
        "termin": (
            "/api/termine",
            {
                "vorgang_id": str(vorgang_id),
                "techniker_id": str(techniker.id),
                "titel": "Termin",
                "start_at": start.isoformat(),
                "ende_at": (start + timedelta(hours=1)).isoformat(),
            },
        ),
    }
    ergebnis = {}
    for name, (pfad, body) in anfragen.items():
        resp = await client.post(pfad, headers=headers, json=body)
        assert resp.status_code == 201, (name, resp.text)
        ergebnis[name] = resp.json()["termin"] if name == "termin" else resp.json()
    return ergebnis


@pytest.mark.asyncio
async def test_erstellt_via_ki_nur_bei_mcp_token(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    per_ki = await _anlegen(client, auth_headers(_mcp_token(admin)), admin, vorgang.id, kunde.id)
    assert {k: v["erstellt_via"] for k, v in per_ki.items()} == dict.fromkeys(per_ki, "ki")

    per_app = await _anlegen(client, auth_headers(await login(client, admin.email, "pw-123456")), admin, vorgang.id, kunde.id)
    assert {k: v["erstellt_via"] for k, v in per_app.items()} == dict.fromkeys(per_app, "app")

    # Auch in der Detailansicht und der Liste sichtbar.
    detail = await client.get(f"/api/vorgaenge/{per_ki['vorgang']['id']}", headers=auth_headers(await login(client, admin.email, "pw-123456")))
    assert detail.json()["erstellt_via"] == "ki"


@pytest.mark.asyncio
async def test_erstellt_via_bei_abgeleiteten_anlagen(client, make_mandant, make_user, make_kunde, make_vorgang):
    """Folge-Auftrag aus einem Vorgang und Angebot aus Vorgang erben die Herkunft des aufrufenden Tokens."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    for token, erwartet in ((_mcp_token(admin), "ki"), (await login(client, admin.email, "pw-123456"), "app")):
        h = auth_headers(token)
        folge = await client.post(f"/api/vorgaenge/{vorgang.id}/folge-auftrag", headers=h, json={"leistungstyp": "wartung"})
        assert folge.status_code == 201, folge.text
        assert folge.json()["erstellt_via"] == erwartet
        angebot = await client.post("/api/angebote/from-vorgang", headers=h, json={"vorgang_id": str(vorgang.id)})
        assert angebot.status_code == 201, angebot.text
        assert angebot.json()["erstellt_via"] == erwartet
