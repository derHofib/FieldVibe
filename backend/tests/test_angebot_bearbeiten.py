"""Angebot bearbeiten (Positionen, Steuersatz), Annahme -> Auftrag, Ablauf, Nachfassen."""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select

from app.core.config import get_settings
from app.core.zeit import in_lokal
from app.db.session import system_session
from app.models.angebot import Angebot
from app.models.mandant import Mandant
from app.models.notification import Notification
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent
from app.services import angebot_service
from app.services.scheduler_service import run_angebot_nachfassen
from tests.conftest import auth_headers, login
from tests.test_kundenportal import _kunden_login, _make_zugang

_BACKEND = os.path.dirname(os.path.dirname(__file__))


def _heute() -> date:
    return in_lokal(datetime.now(timezone.utc)).date()


async def _admin(client, make_mandant, make_user, make_kunde, *, kunde_name="Testkunde", mandant=None):
    mandant = mandant or await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    kunde = await make_kunde(mandant=mandant, name=kunde_name)
    token = await login(client, admin.email, "pw-123456")
    return mandant, admin, kunde, auth_headers(token)


POSITIONEN = [
    {"beschreibung": "Kabel", "menge": "10", "einheit": "m", "einzelpreis": "2.50"},
    {"beschreibung": "Montage", "menge": "2", "einheit": "Std", "einzelpreis": "60.00", "positionstyp": "arbeitszeit"},
    {"beschreibung": "Anfahrt", "menge": "1", "einheit": "pausch.", "einzelpreis": "30.00"},
]


async def _angebot(client, headers, kunde, **extra) -> dict:
    body = {"kunde_id": str(kunde.id), "positionen": POSITIONEN, **extra}
    resp = await client.post("/api/angebote", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _versenden(client, headers, angebot_id):
    resp = await client.patch(f"/api/angebote/{angebot_id}", headers=headers, json={"status": "versendet"})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _setze(angebot_id, **felder):
    async with system_session() as session:
        angebot = await session.get(Angebot, angebot_id)
        for k, v in felder.items():
            setattr(angebot, k, v)
        await session.commit()


async def _anzahl_vorgaenge(mandant) -> int:
    async with system_session() as session:
        return (
            await session.execute(select(func.count()).select_from(Vorgang).where(Vorgang.mandant_id == mandant.id))
        ).scalar_one()


# --- Positionen --------------------------------------------------------------


async def test_position_bearbeiten_aktualisiert_summen(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    assert angebot["gesamt_netto"] == "175.00"
    pos = angebot["positionen"][0]

    resp = await client.patch(
        f"/api/angebote/{angebot['id']}/positionen/{pos['id']}",
        headers=h,
        json={"beschreibung": "Kabel NYM", "menge": "20", "einheit": "lfm", "einzelpreis": "3.00",
              "artikelnummer": "B-1", "positionstyp": "material"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    neu = body["positionen"][0]
    assert (neu["beschreibung"], Decimal(neu["menge"]), neu["einheit"], Decimal(neu["einzelpreis"])) == (
        "Kabel NYM", Decimal("20"), "lfm", Decimal("3"),
    )
    assert neu["artikelnummer"] == "B-1"
    assert neu["gesamt"] == "60.00"
    assert body["gesamt_netto"] == "210.00"
    assert body["gesamt_brutto"] == "249.90"

    # Teil-PATCH laesst den Rest unveraendert, die Artikelnummer ist leerbar.
    resp = await client.patch(
        f"/api/angebote/{angebot['id']}/positionen/{pos['id']}", headers=h, json={"artikelnummer": None}
    )
    assert resp.status_code == 200
    assert resp.json()["positionen"][0]["artikelnummer"] is None
    assert Decimal(resp.json()["positionen"][0]["menge"]) == 20


@pytest.mark.parametrize(
    "payload",
    [{"menge": "0"}, {"menge": "-1"}, {"einzelpreis": "-0.01"}, {"beschreibung": None}, {"beschreibung": ""},
     {"menge": None}, {"positionstyp": "sonstiges"}],
)
async def test_position_bearbeiten_validiert(client, make_mandant, make_user, make_kunde, payload):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    resp = await client.patch(
        f"/api/angebote/{angebot['id']}/positionen/{angebot['positionen'][0]['id']}", headers=h, json=payload
    )
    assert resp.status_code == 422


async def test_position_preis_null_ist_erlaubt(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    resp = await client.patch(
        f"/api/angebote/{angebot['id']}/positionen/{angebot['positionen'][0]['id']}",
        headers=h,
        json={"einzelpreis": "0"},
    )
    assert resp.status_code == 200
    assert resp.json()["gesamt_netto"] == "150.00"


async def test_position_loeschen_nummeriert_lueckenlos(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    mitte = angebot["positionen"][1]

    resp = await client.delete(f"/api/angebote/{angebot['id']}/positionen/{mitte['id']}", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(p["position"], p["beschreibung"]) for p in body["positionen"]] == [(1, "Kabel"), (2, "Anfahrt")]
    assert body["gesamt_netto"] == "55.00"

    # Auch die letzte Position darf weg; ein Angebot ohne Positionen bleibt Entwurf.
    for p in body["positionen"]:
        resp = await client.delete(f"/api/angebote/{angebot['id']}/positionen/{p['id']}", headers=h)
        assert resp.status_code == 200
    assert resp.json()["positionen"] == []
    assert resp.json()["gesamt_brutto"] == "0.00"


async def test_positionen_neu_ordnen(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    ids = [p["id"] for p in angebot["positionen"]]

    resp = await client.post(
        f"/api/angebote/{angebot['id']}/positionen/neu-ordnen", headers=h, json={"position_ids": [ids[2], ids[0], ids[1]]}
    )
    assert resp.status_code == 200, resp.text
    assert [(p["position"], p["id"]) for p in resp.json()["positionen"]] == [(1, ids[2]), (2, ids[0]), (3, ids[1])]
    assert resp.json()["gesamt_netto"] == "175.00"

    # Neue Position hängt hinten an, die Reihenfolge bleibt erhalten.
    resp = await client.post(
        f"/api/angebote/{angebot['id']}/positionen", headers=h, json={"beschreibung": "Nachtrag", "einzelpreis": "1"}
    )
    assert [p["position"] for p in resp.json()["positionen"]] == [1, 2, 3, 4]
    assert resp.json()["positionen"][0]["id"] == ids[2]


async def test_positionen_neu_ordnen_verlangt_exakt_die_vorhandenen_ids(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    anderes = await _angebot(client, h, kunde)
    ids = [p["id"] for p in angebot["positionen"]]
    url = f"/api/angebote/{angebot['id']}/positionen/neu-ordnen"

    for falsch in (
        ids[:2],  # fehlt eine
        [*ids, ids[0]],  # doppelt
        [ids[0], ids[0], ids[1]],  # doppelt statt vollstaendig
        [*ids[:2], anderes["positionen"][0]["id"]],  # fremde Position
        [],
    ):
        resp = await client.post(url, headers=h, json={"position_ids": falsch})
        assert resp.status_code == 422, falsch

    unveraendert = await client.get(f"/api/angebote/{angebot['id']}", headers=h)
    assert [p["id"] for p in unveraendert.json()["positionen"]] == ids


async def test_positionen_nur_im_entwurf_aenderbar(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    ids = [p["id"] for p in angebot["positionen"]]
    await _versenden(client, h, angebot["id"])
    basis = f"/api/angebote/{angebot['id']}/positionen"

    antworten = [
        await client.patch(f"{basis}/{ids[0]}", headers=h, json={"menge": "5"}),
        await client.delete(f"{basis}/{ids[0]}", headers=h),
        await client.post(f"{basis}/neu-ordnen", headers=h, json={"position_ids": ids[::-1]}),
    ]
    for resp in antworten:
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Angebot ist nicht mehr bearbeitbar"

    unveraendert = await client.get(f"/api/angebote/{angebot['id']}", headers=h)
    assert unveraendert.json()["gesamt_netto"] == "175.00"
    assert [p["id"] for p in unveraendert.json()["positionen"]] == ids


async def test_positionen_fremder_mandant_und_fremde_position_404(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    _, _, _, h_fremd = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    anderes = await _angebot(client, h, kunde)
    ids = [p["id"] for p in angebot["positionen"]]
    basis = f"/api/angebote/{angebot['id']}/positionen"

    assert (await client.patch(f"{basis}/{ids[0]}", headers=h_fremd, json={"menge": "9"})).status_code == 404
    assert (await client.delete(f"{basis}/{ids[0]}", headers=h_fremd)).status_code == 404
    assert (
        await client.post(f"{basis}/neu-ordnen", headers=h_fremd, json={"position_ids": ids})
    ).status_code == 404

    # Position eines anderen Angebots (gleicher Mandant) ueber die falsche Angebots-ID.
    fremde_position = anderes["positionen"][0]["id"]
    assert (await client.patch(f"{basis}/{fremde_position}", headers=h, json={"menge": "9"})).status_code == 404
    assert (await client.delete(f"{basis}/{fremde_position}", headers=h)).status_code == 404
    assert (
        await client.patch(
            f"{basis}/00000000-0000-0000-0000-000000000000", headers=h, json={"menge": "9"}
        )
    ).status_code == 404

    unveraendert = await client.get(f"/api/angebote/{anderes['id']}", headers=h)
    assert unveraendert.json()["gesamt_netto"] == "175.00"


# --- Steuersatz --------------------------------------------------------------


@pytest.mark.parametrize("satz,brutto", [("19", "208.25"), ("7", "187.25"), ("0", "175.00")])
async def test_steuersatz_bei_anlage_waehlbar(client, make_mandant, make_user, make_kunde, satz, brutto):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde, mwst_satz=satz)
    assert Decimal(angebot["mwst_satz"]) == Decimal(satz)
    assert angebot["gesamt_brutto"] == brutto


async def test_steuersatz_default_ist_19(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    assert Decimal((await _angebot(client, h, kunde))["mwst_satz"]) == Decimal("19")


@pytest.mark.parametrize("satz", ["5", "19.5", "-7", "100"])
async def test_ungueltiger_steuersatz_422(client, make_mandant, make_user, make_kunde, satz):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    resp = await client.post("/api/angebote", headers=h, json={"kunde_id": str(kunde.id), "mwst_satz": satz})
    assert resp.status_code == 422
    angebot = await _angebot(client, h, kunde)
    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"mwst_satz": satz})
    assert resp.status_code == 422


async def test_steuersatz_aendern_nur_im_entwurf(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)

    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"mwst_satz": "7"})
    assert resp.status_code == 200
    assert resp.json()["gesamt_brutto"] == "187.25"

    await _versenden(client, h, angebot["id"])
    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"mwst_satz": "0"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Angebot ist nicht mehr bearbeitbar"
    # Derselbe Satz ist keine Aenderung.
    assert (await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"mwst_satz": "7"})).status_code == 200
    assert (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()["gesamt_brutto"] == "187.25"


async def test_kleinunternehmer_erzwingt_steuersatz_null(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    async with system_session() as session:
        (await session.get(Mandant, mandant.id)).firmendaten = {"ist_kleinunternehmer": True}
        await session.commit()
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, mandant=mandant)

    angebot = await _angebot(client, h, kunde, mwst_satz="19")
    assert Decimal(angebot["mwst_satz"]) == 0
    assert angebot["gesamt_brutto"] == "175.00"

    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"mwst_satz": "7"})
    assert resp.status_code == 200
    assert Decimal(resp.json()["mwst_satz"]) == 0

    # Auch die bestehenden Anlage-Wege (hier: aus Vorgang) nehmen 0 %.
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    resp = await client.post("/api/angebote/from-vorgang", headers=h, json={"vorgang_id": str(vorgang.id)})
    assert resp.status_code == 201
    assert Decimal(resp.json()["mwst_satz"]) == 0


async def test_summen_runden_kaufmaennisch(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    # 1,50 EUR x 7 % = 0,105: HALF_UP -> 0,11 (HALF_EVEN haette 0,10 ergeben).
    resp = await client.post(
        "/api/angebote",
        headers=h,
        json={
            "kunde_id": str(kunde.id),
            "mwst_satz": "7",
            "positionen": [{"beschreibung": "Teil", "menge": "3", "einzelpreis": "0.50"}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["gesamt_netto"] == "1.50"
    assert resp.json()["gesamt_brutto"] == "1.61"

    # Netto wird aus der Summe gerundet, nicht je Position: 0,33 x 0,25 = 0,0825.
    resp = await client.patch(
        f"/api/angebote/{resp.json()['id']}/positionen/{resp.json()['positionen'][0]['id']}",
        headers=h,
        json={"menge": "0.33", "einzelpreis": "0.25"},
    )
    assert resp.json()["gesamt_netto"] == "0.08"
    assert resp.json()["positionen"][0]["gesamt"] == "0.08"


# --- Annahme erzeugt Auftrag -------------------------------------------------


async def test_annahme_ohne_vorgang_legt_auftrag_an(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])
    assert await _anzahl_vorgaenge(mandant) == 0

    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    assert resp.status_code == 200, resp.text
    auftrag_id = resp.json()["auftrag_vorgang_id"]
    assert auftrag_id is not None
    assert await _anzahl_vorgaenge(mandant) == 1

    async with system_session() as session:
        from uuid import UUID

        vorgang = await session.get(Vorgang, UUID(auftrag_id))
        assert vorgang.titel == f"Auftrag aus Angebot {angebot['angebotsnummer']}"
        assert vorgang.kunde_id == kunde.id
        assert vorgang.abrechnungsart == "festpreis"
        assert vorgang.leistungstyp == "installation"
        assert vorgang.vorgangsnummer
        events = (
            (await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))).scalars().all()
        )
        assert [(e.event_type, e.is_system, e.body) for e in events] == [
            ("system", True, f"Angelegt aus angenommenem Angebot {angebot['angebotsnummer']}")
        ]
        assert events[0].payload == {"angebot_id": angebot["id"]}

    # Zugehoeriger Vorgang ist ueber die API sichtbar (Mandantentrennung/RLS greift normal).
    assert (await client.get(f"/api/vorgaenge/{auftrag_id}", headers=h)).status_code == 200


async def test_annahme_mit_bestehendem_vorgang_legt_keinen_neuen_an(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)
    angebot = await _angebot(client, h, kunde, vorgang_id=str(vorgang.id))
    await _versenden(client, h, angebot["id"])

    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    assert resp.status_code == 200
    assert resp.json()["auftrag_vorgang_id"] == str(vorgang.id)
    assert await _anzahl_vorgaenge(mandant) == 1

    async with system_session() as session:
        events = (
            (await session.execute(select(VorgangEvent).where(VorgangEvent.vorgang_id == vorgang.id))).scalars().all()
        )
        assert [e.body for e in events if e.event_type == "angebot" and e.payload.get("status") == "angenommen"] == [
            f"Angebot {angebot['angebotsnummer']}: Status 'angenommen'"
        ]
        assert not [e for e in events if e.is_system]


async def test_annahme_ueber_kundenportal_erzeugt_denselben_auftrag(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    await _make_zugang(mandant, kunde, email="portal-auftrag@example.de")
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])

    tokens = await _kunden_login(client, "portal-auftrag@example.de", "kunden-pw-123")
    resp = await client.patch(
        f"/api/kundenportal/angebote/{angebot['id']}",
        headers=auth_headers(tokens["access_token"]),
        json={"status": "angenommen"},
    )
    assert resp.status_code == 200, resp.text
    # Das Portal gibt die interne Auftrags-ID nicht heraus (Whitelist-Schema).
    assert "auftrag_vorgang_id" not in resp.json()
    assert await _anzahl_vorgaenge(mandant) == 1

    intern = await client.get(f"/api/angebote/{angebot['id']}", headers=h)
    assert intern.json()["auftrag_vorgang_id"] is not None
    assert intern.json()["status"] == "angenommen"


async def test_doppelte_annahme_erzeugt_keinen_zweiten_auftrag(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])

    erste = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    zweite = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    assert erste.status_code == 200
    assert zweite.status_code == 400
    assert (await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "abgelehnt"})).status_code == 400
    assert await _anzahl_vorgaenge(mandant) == 1
    assert (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()["auftrag_vorgang_id"] == erste.json()[
        "auftrag_vorgang_id"
    ]


async def test_gleichzeitige_annahme_erzeugt_genau_einen_auftrag(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])

    antworten = await asyncio.gather(
        *[client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"}) for _ in range(2)]
    )
    assert sorted(r.status_code for r in antworten) == [200, 400]
    assert await _anzahl_vorgaenge(mandant) == 1


async def test_ablehnung_legt_keinen_auftrag_an(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])
    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "abgelehnt"})
    assert resp.json()["auftrag_vorgang_id"] is None
    assert await _anzahl_vorgaenge(mandant) == 0


# --- Ablauf ------------------------------------------------------------------


async def test_abgelaufenes_angebot_nicht_annehmbar_intern_und_portal(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    await _make_zugang(mandant, kunde, email="portal-abgelaufen@example.de")
    angebot = await _angebot(client, h, kunde, gueltig_bis=(_heute() - timedelta(days=1)).isoformat())
    versendet = await _versenden(client, h, angebot["id"])
    assert versendet["ist_abgelaufen"] is True

    intern = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    assert intern.status_code == 400
    assert intern.json()["detail"] == "Das Angebot ist abgelaufen"

    tokens = await _kunden_login(client, "portal-abgelaufen@example.de", "kunden-pw-123")
    kh = auth_headers(tokens["access_token"])
    gelesen = await client.get(f"/api/kundenportal/angebote/{angebot['id']}", headers=kh)
    assert gelesen.json()["ist_abgelaufen"] is True
    portal = await client.patch(
        f"/api/kundenportal/angebote/{angebot['id']}", headers=kh, json={"status": "angenommen"}
    )
    assert portal.status_code == 400
    assert portal.json()["detail"] == "Das Angebot ist abgelaufen"

    nach = (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()
    assert nach["status"] == "versendet"
    assert nach["angenommen_am"] is None
    assert await _anzahl_vorgaenge(mandant) == 0

    # Ablehnen bleibt moeglich.
    assert (
        await client.patch(f"/api/kundenportal/angebote/{angebot['id']}", headers=kh, json={"status": "abgelehnt"})
    ).status_code == 200


async def test_verlaengerung_macht_abgelaufenes_angebot_wieder_annehmbar(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde, gueltig_bis=(_heute() - timedelta(days=3)).isoformat())
    await _versenden(client, h, angebot["id"])
    assert (await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})).status_code == 400

    neu = (_heute() + timedelta(days=14)).isoformat()
    resp = await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"gueltig_bis": neu})
    assert resp.status_code == 200
    assert resp.json()["ist_abgelaufen"] is False
    assert resp.json()["gueltig_bis"] == neu

    assert (await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})).status_code == 200


async def test_verlaengern_und_annehmen_in_einem_patch(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde, gueltig_bis=(_heute() - timedelta(days=1)).isoformat())
    await _versenden(client, h, angebot["id"])
    resp = await client.patch(
        f"/api/angebote/{angebot['id']}",
        headers=h,
        json={"gueltig_bis": (_heute() + timedelta(days=1)).isoformat(), "status": "angenommen"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "angenommen"


async def test_gueltigkeit_nach_annahme_nicht_mehr_aenderbar(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    angebot = await _angebot(client, h, kunde)
    await _versenden(client, h, angebot["id"])
    await client.patch(f"/api/angebote/{angebot['id']}", headers=h, json={"status": "angenommen"})
    resp = await client.patch(
        f"/api/angebote/{angebot['id']}", headers=h, json={"gueltig_bis": _heute().isoformat()}
    )
    assert resp.status_code == 400


async def test_ist_abgelaufen_nur_fuer_versendete_mit_vergangenem_datum(client, make_mandant, make_user, make_kunde):
    _, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    gestern = (_heute() - timedelta(days=1)).isoformat()
    entwurf = await _angebot(client, h, kunde, gueltig_bis=gestern)
    assert entwurf["ist_abgelaufen"] is False  # Entwurf laeuft nicht ab

    ohne_datum = await _angebot(client, h, kunde)
    assert (await _versenden(client, h, ohne_datum["id"]))["ist_abgelaufen"] is False

    heute_gueltig = await _angebot(client, h, kunde, gueltig_bis=_heute().isoformat())
    assert (await _versenden(client, h, heute_gueltig["id"]))["ist_abgelaufen"] is False  # einschliesslich heute

    angenommen = await _angebot(client, h, kunde, gueltig_bis=_heute().isoformat())
    await _versenden(client, h, angenommen["id"])
    await client.patch(f"/api/angebote/{angenommen['id']}", headers=h, json={"status": "angenommen"})
    await _setze(angenommen["id"], gueltig_bis=date.fromisoformat(gestern))
    assert (await client.get(f"/api/angebote/{angenommen['id']}", headers=h)).json()["ist_abgelaufen"] is False


def test_ist_abgelaufen_tagesgrenze_in_betriebszeitzone(monkeypatch):
    """23:30 UTC am 18.10. ist in Berlin (MESZ) schon der 19.10. -- ein UTC-Tag
    wuerde das Angebot vom 18.10. noch als gueltig zeigen."""
    angebot = Angebot(status="versendet", gueltig_bis=date(2026, 10, 18))

    class _Jetzt(datetime):
        zeitpunkt = datetime(2026, 10, 18, 23, 30, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.zeitpunkt.astimezone(tz) if tz else cls.zeitpunkt

    monkeypatch.setattr(angebot_service, "datetime", _Jetzt)
    assert get_settings().zeitzone == "Europe/Berlin"
    assert angebot_service.ist_abgelaufen(angebot) is True

    _Jetzt.zeitpunkt = datetime(2026, 10, 18, 21, 59, tzinfo=timezone.utc)  # 23:59 Berlin, noch der 18.
    assert angebot_service.ist_abgelaufen(angebot) is False

    assert angebot_service.ist_abgelaufen(angebot, heute=date(2026, 10, 18)) is False
    assert angebot_service.ist_abgelaufen(angebot, heute=date(2026, 10, 19)) is True
    angebot.status = "angenommen"
    assert angebot_service.ist_abgelaufen(angebot, heute=date(2026, 10, 19)) is False


# --- Nachfassen --------------------------------------------------------------


async def _versendetes_angebot(client, h, kunde, *, versendet_vor_tagen=0, gueltig_bis=None, ersteller=None) -> dict:
    angebot = await _angebot(client, h, kunde, gueltig_bis=gueltig_bis.isoformat() if gueltig_bis else None)
    await _versenden(client, h, angebot["id"])
    felder = {"versendet_am": datetime.now(timezone.utc) - timedelta(days=versendet_vor_tagen)}
    if ersteller is not None:
        felder["erstellt_von"] = ersteller.id
    from uuid import UUID

    await _setze(UUID(angebot["id"]), **felder)
    return angebot


async def _benachrichtigungen(mandant=None) -> list[Notification]:
    async with system_session() as session:
        stmt = select(Notification).where(Notification.typ == "angebot").order_by(Notification.id)
        if mandant is not None:
            stmt = stmt.where(Notification.mandant_id == mandant.id)
        return list((await session.execute(stmt)).scalars().all())


async def test_nachfassen_nach_n_tagen_genau_einmal(client, make_mandant, make_user, make_kunde):
    mandant, admin, kunde, h = await _admin(client, make_mandant, make_user, make_kunde, kunde_name="Müller GmbH")
    angebot = await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=8)

    ergebnis = await run_angebot_nachfassen([mandant.id])
    assert ergebnis == {"angebote_benachrichtigt": 1}
    eintraege = await _benachrichtigungen(mandant)
    assert len(eintraege) == 1
    n = eintraege[0]
    assert n.user_id == admin.id
    assert (n.ref_entity_type, str(n.ref_entity_id)) == ("angebot", angebot["id"])
    assert angebot["angebotsnummer"] in n.titel
    assert "Müller GmbH" in n.titel
    assert "208,25 € brutto" in n.titel
    assert "seit 8 Tagen unbeantwortet" in n.titel

    async with system_session() as session:
        from uuid import UUID

        assert (await session.get(Angebot, UUID(angebot["id"]))).nachgefasst_am is not None
    assert (await client.get(f"/api/angebote/{angebot['id']}", headers=h)).json()["nachgefasst_am"] is not None

    # Idempotent: zweiter Lauf (auch ohne Mandantenfilter) erzeugt nichts.
    assert await run_angebot_nachfassen([mandant.id]) == {"angebote_benachrichtigt": 0}
    assert await run_angebot_nachfassen() == {"angebote_benachrichtigt": 0}
    assert len(await _benachrichtigungen(mandant)) == 1


async def test_nachfassen_schwelle_aus_settings(client, make_mandant, make_user, make_kunde, monkeypatch):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=5)
    assert (await run_angebot_nachfassen([mandant.id]))["angebote_benachrichtigt"] == 0  # Default 7 Tage

    monkeypatch.setattr(get_settings(), "angebot_nachfass_tage", 5)
    assert (await run_angebot_nachfassen([mandant.id]))["angebote_benachrichtigt"] == 1


async def test_nachfassen_bei_ablauf_in_zwei_tagen(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    in_zwei = await _versendetes_angebot(client, h, kunde, gueltig_bis=_heute() + timedelta(days=2))
    await _versendetes_angebot(client, h, kunde, gueltig_bis=_heute() + timedelta(days=3))
    await _versendetes_angebot(client, h, kunde)

    assert (await run_angebot_nachfassen([mandant.id]))["angebote_benachrichtigt"] == 1
    eintraege = await _benachrichtigungen(mandant)
    assert [str(n.ref_entity_id) for n in eintraege] == [in_zwei["id"]]
    assert "läuft am" in eintraege[0].titel and "ab" in eintraege[0].titel


async def test_nachfassen_auch_bei_bereits_abgelaufenem_angebot(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    await _versendetes_angebot(client, h, kunde, gueltig_bis=_heute() - timedelta(days=1))
    assert (await run_angebot_nachfassen([mandant.id]))["angebote_benachrichtigt"] == 1
    assert "ist abgelaufen" in (await _benachrichtigungen(mandant))[0].titel


async def test_nachfassen_nur_fuer_versendete_angebote(client, make_mandant, make_user, make_kunde):
    mandant, _, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    from uuid import UUID

    alt = datetime.now(timezone.utc) - timedelta(days=30)
    bald = _heute() + timedelta(days=1)

    entwurf = await _angebot(client, h, kunde, gueltig_bis=bald.isoformat())
    await _setze(UUID(entwurf["id"]), versendet_am=alt)

    angenommen = await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=30, gueltig_bis=bald)
    await client.patch(f"/api/angebote/{angenommen['id']}", headers=h, json={"status": "angenommen"})

    abgelehnt = await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=30, gueltig_bis=bald)
    await client.patch(f"/api/angebote/{abgelehnt['id']}", headers=h, json={"status": "abgelehnt"})

    geloescht = await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=30)
    await _setze(UUID(geloescht["id"]), geloescht_am=datetime.now(timezone.utc))

    assert await run_angebot_nachfassen([mandant.id]) == {"angebote_benachrichtigt": 0}
    assert await _benachrichtigungen(mandant) == []


async def test_nachfassen_mandantentrennung(client, make_mandant, make_user, make_kunde):
    m1, admin1, kunde1, h1 = await _admin(client, make_mandant, make_user, make_kunde)
    m2, admin2, kunde2, h2 = await _admin(client, make_mandant, make_user, make_kunde)
    await _versendetes_angebot(client, h1, kunde1, versendet_vor_tagen=10)
    await _versendetes_angebot(client, h2, kunde2, versendet_vor_tagen=10)

    assert (await run_angebot_nachfassen([m1.id]))["angebote_benachrichtigt"] == 1
    assert [n.user_id for n in await _benachrichtigungen()] == [admin1.id]

    assert (await run_angebot_nachfassen([m2.id]))["angebote_benachrichtigt"] == 1
    assert sorted(str(n.user_id) for n in await _benachrichtigungen()) == sorted([str(admin1.id), str(admin2.id)])

    # Jede Benachrichtigung zeigt auf ein Angebot des eigenen Mandanten.
    async with system_session() as session:
        for n in await _benachrichtigungen():
            assert (await session.get(Angebot, n.ref_entity_id)).mandant_id == n.mandant_id


async def test_nachfassen_geht_an_den_ersteller_nicht_an_andere(client, make_mandant, make_user, make_kunde):
    mandant, admin, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    ersteller = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=9, ersteller=ersteller)
    await run_angebot_nachfassen([mandant.id])
    assert [n.user_id for n in await _benachrichtigungen(mandant)] == [ersteller.id]


async def test_nachfassen_inaktiver_ersteller_faellt_auf_admins_zurueck(client, make_mandant, make_user, make_kunde):
    mandant, admin, kunde, h = await _admin(client, make_mandant, make_user, make_kunde)
    weg = await make_user(mandant=mandant, role="mandant_admin", aktiv=False)
    await _versendetes_angebot(client, h, kunde, versendet_vor_tagen=9, ersteller=weg)
    await run_angebot_nachfassen([mandant.id])
    empfaenger = {n.user_id for n in await _benachrichtigungen(mandant)}
    assert admin.id in empfaenger
    assert weg.id not in empfaenger


# --- Migration ---------------------------------------------------------------


def _cfg() -> Config:
    cfg = Config(os.path.join(_BACKEND, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(_BACKEND, "alembic"))
    return cfg


async def _migrieren(richtung: str, ziel: str) -> None:
    await asyncio.to_thread(getattr(command, richtung), _cfg(), ziel)


async def test_migration_0107_up_down_up():
    engine = create_engine(os.environ.get("DATABASE_URL_SYNC") or get_settings().database_url_sync)
    neu = {"auftrag_vorgang_id", "nachgefasst_am"}

    def spalten() -> dict:
        return {c["name"]: c for c in inspect(engine).get_columns("angebote")}

    def fks() -> set:
        return {fk["name"] for fk in inspect(engine).get_foreign_keys("angebote")}

    try:
        await _migrieren("downgrade", "0106")
        assert not neu & spalten().keys()
        assert "fk_angebote_auftrag_vorgang_id_vorgaenge" not in fks()

        await _migrieren("upgrade", "head")
        gefunden = spalten()
        assert neu <= gefunden.keys()
        assert all(gefunden[name]["nullable"] for name in neu)
        assert "fk_angebote_auftrag_vorgang_id_vorgaenge" in fks()
    finally:
        await _migrieren("upgrade", "head")
        engine.dispose()
