import base64

import pytest

from tests.conftest import auth_headers, login


async def _make_published_schema(client, token, *, name="Wartungsprotokoll"):
    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": name})
    ).json()
    await client.patch(
        f"/api/form-schemas/{schema['id']}", headers=auth_headers(token), json={"status": "published"}
    )
    return schema


@pytest.mark.asyncio
async def test_schema_crud_und_key_konflikt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")

    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": "Test"})
    ).json()
    assert schema["status"] == "draft"
    assert schema["version"] == 1

    feld = (
        await client.post(
            f"/api/form-schemas/{schema['id']}/fields",
            headers=auth_headers(token),
            json={"key": "kommentar", "feld_typ": "text", "label": {"de": "Kommentar"}},
        )
    ).json()
    assert feld["key"] == "kommentar"

    konflikt = await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kommentar", "feld_typ": "zahl"},
    )
    assert konflikt.status_code == 409

    detail = (await client.get(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token))).json()
    assert len(detail["fields"]) == 1


@pytest.mark.asyncio
async def test_feld_in_unbekannter_gruppe_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": "Test"})
    ).json()

    resp = await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kosten", "feld_typ": "zahl", "group_key": "nicht_vorhanden"},
    )
    assert resp.status_code == 400

    gruppe = (
        await client.post(
            f"/api/form-schemas/{schema['id']}/groups",
            headers=auth_headers(token),
            json={"key": "maengel"},
        )
    ).json()
    ok = await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kosten", "feld_typ": "zahl", "group_key": gruppe["key"]},
    )
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_regel_mit_unbekanntem_target_key_wird_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": "Test"})
    ).json()

    resp = await client.post(
        f"/api/form-schemas/{schema['id']}/rules",
        headers=auth_headers(token),
        json={"target_key": "unbekannt", "effect": "show", "condition": True},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_zyklische_set_value_regeln_werden_abgelehnt(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": "Test"})
    ).json()
    for key in ("x", "y"):
        await client.post(
            f"/api/form-schemas/{schema['id']}/fields",
            headers=auth_headers(token),
            json={"key": key, "feld_typ": "text"},
        )

    ok = await client.post(
        f"/api/form-schemas/{schema['id']}/rules",
        headers=auth_headers(token),
        json={"target_key": "x", "effect": "set_value", "condition": {"==": [{"var": "y"}, 1]}, "value": "X"},
    )
    assert ok.status_code == 201

    zyklus = await client.post(
        f"/api/form-schemas/{schema['id']}/rules",
        headers=auth_headers(token),
        json={"target_key": "y", "effect": "set_value", "condition": {"==": [{"var": "x"}, 1]}, "value": "Y"},
    )
    assert zyklus.status_code == 409


@pytest.mark.asyncio
async def test_view_layouts_bulk_replace(client, make_mandant, make_user):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    schema = (
        await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": "Test"})
    ).json()
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kommentar", "feld_typ": "text"},
    )
    view = (
        await client.post(
            f"/api/form-schemas/{schema['id']}/views",
            headers=auth_headers(token),
            json={"type": "capture", "name": "Erfassung"},
        )
    ).json()

    unbekannt = await client.put(
        f"/api/form-schemas/{schema['id']}/views/{view['id']}/layouts",
        headers=auth_headers(token),
        json=[{"field_key": "existiert_nicht"}],
    )
    assert unbekannt.status_code == 400

    ok = await client.put(
        f"/api/form-schemas/{schema['id']}/views/{view['id']}/layouts",
        headers=auth_headers(token),
        json=[{"field_key": "kommentar", "x_mm": 5, "y_mm": 5}],
    )
    assert ok.status_code == 200
    assert len(ok.json()) == 1
    assert ok.json()[0]["x_mm"] == 5


@pytest.mark.asyncio
async def test_submission_lifecycle_mit_autofill_audit_und_pflichtfeld(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant, name="Musterkunde")
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, leistungstyp="wartung")

    schema = await _make_published_schema(client, token)
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kunde_name", "feld_typ": "text", "datenquelle": "kunde.name"},
    )
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "zustand", "feld_typ": "dropdown", "pflichtfeld": True},
    )
    await client.post(
        f"/api/form-schemas/{schema['id']}/zuordnungen",
        headers=auth_headers(token),
        json={"leistungstyp": "wartung", "pflicht_vor_abschluss": True},
    )

    verfuegbar = (
        await client.get(
            "/api/form-submissions/verfuegbar", headers=auth_headers(token), params={"vorgang_id": str(vorgang.id)}
        )
    ).json()
    assert any(s["id"] == schema["id"] for s in verfuegbar)

    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()
    assert submission["values"]["kunde_name"] == "Musterkunde"
    assert submission["schema_version"] == 1

    zu_frueh = await client.post(
        f"/api/form-submissions/{submission['id']}/abschliessen", headers=auth_headers(token)
    )
    assert zu_frueh.status_code == 400
    assert "zustand" in zu_frueh.json()["detail"].lower() or "Pflichtfelder" in zu_frueh.json()["detail"]

    patched = (
        await client.patch(
            f"/api/form-submissions/{submission['id']}",
            headers=auth_headers(token),
            json={"values": {"zustand": "gut"}},
        )
    ).json()
    assert patched["values"]["zustand"] == "gut"
    assert patched["values"]["kunde_name"] == "Musterkunde"

    fertig = await client.post(
        f"/api/form-submissions/{submission['id']}/abschliessen", headers=auth_headers(token)
    )
    assert fertig.status_code == 200
    assert fertig.json()["status"] == "abgeschlossen"

    nochmal = await client.post(
        f"/api/form-submissions/{submission['id']}/abschliessen", headers=auth_headers(token)
    )
    assert nochmal.status_code == 409


@pytest.mark.asyncio
async def test_pflichtfeld_wird_durch_hide_regel_ausser_kraft_gesetzt(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    """Belegt die identische Regel-Auswertung Backend/Frontend an der
    entscheidenden Stelle: ein per Regel ausgeblendetes Pflichtfeld darf den
    Abschluss NICHT blockieren -- dieselbe form_logic_engine wie im
    Frontend (formLogicEngine.ts) entscheidet hier serverseitig."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    schema = await _make_published_schema(client, token)
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "schalter", "feld_typ": "ja_nein"},
    )
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "detail", "feld_typ": "text", "pflichtfeld": True},
    )
    await client.post(
        f"/api/form-schemas/{schema['id']}/rules",
        headers=auth_headers(token),
        json={"target_key": "detail", "effect": "hide", "condition": {"==": [{"var": "schalter"}, False]}},
    )

    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()
    await client.patch(
        f"/api/form-submissions/{submission['id']}",
        headers=auth_headers(token),
        json={"values": {"schalter": False}},
    )

    fertig = await client.post(
        f"/api/form-submissions/{submission['id']}/abschliessen", headers=auth_headers(token)
    )
    assert fertig.status_code == 200


@pytest.mark.asyncio
async def test_submission_pdf_ueber_print_view(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    schema = await _make_published_schema(client, token, name="Protokoll")
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={"key": "kommentar", "feld_typ": "text", "label": {"de": "Kommentar"}},
    )
    print_view = (
        await client.post(
            f"/api/form-schemas/{schema['id']}/views",
            headers=auth_headers(token),
            json={"type": "print", "name": "Ausdruck"},
        )
    ).json()
    await client.put(
        f"/api/form-schemas/{schema['id']}/views/{print_view['id']}/layouts",
        headers=auth_headers(token),
        json=[{"field_key": "kommentar", "x_mm": 0, "y_mm": 0}],
    )

    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()
    await client.patch(
        f"/api/form-submissions/{submission['id']}",
        headers=auth_headers(token),
        json={"values": {"kommentar": "Alles in Ordnung"}},
    )

    resp = await client.get(f"/api/form-submissions/{submission['id']}/pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "Vorschau-" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_abschliessen_erzeugt_vorgang_event_fuer_feed(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    schema = await _make_published_schema(client, token, name="Wartungsprotokoll")
    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()
    await client.post(f"/api/form-submissions/{submission['id']}/abschliessen", headers=auth_headers(token))

    events = (await client.get(f"/api/vorgaenge/{vorgang.id}/events", headers=auth_headers(token))).json()
    formular_events = [e for e in events if e["event_type"] == "formular"]
    assert len(formular_events) == 1
    assert formular_events[0]["body"] == "Wartungsprotokoll"
    assert formular_events[0]["ref_entity_type"] == "form_submission"
    assert formular_events[0]["ref_entity_id"] == submission["id"]


@pytest.mark.asyncio
async def test_rls_isolation_form_schemas_und_submissions(
    client, make_mandant, make_user, make_kunde, make_vorgang
):
    mandant_a = await make_mandant(name="A")
    mandant_b = await make_mandant(name="B")
    admin_a = await make_user(mandant=mandant_a, role="mandant_admin", password="pw-123456")
    admin_b = await make_user(mandant=mandant_b, role="mandant_admin", password="pw-123456")
    token_a = await login(client, admin_a.email, "pw-123456")
    token_b = await login(client, admin_b.email, "pw-123456")

    schema = await _make_published_schema(client, token_a, name="Nur A")

    resp = await client.get(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token_b))
    assert resp.status_code == 404

    list_resp = await client.get("/api/form-schemas", headers=auth_headers(token_b))
    assert schema["id"] not in [s["id"] for s in list_resp.json()]

    kunde = await make_kunde(mandant=mandant_a)
    vorgang = await make_vorgang(mandant=mandant_a, kunde=kunde)
    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token_a),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()

    fremdzugriff = await client.get(f"/api/form-submissions/{submission['id']}", headers=auth_headers(token_b))
    assert fremdzugriff.status_code == 404


# Kleinstes gueltiges PNG (1x1 Pixel) -- reicht Pillow zum Oeffnen, egal ob
# als Hintergrundfoto oder als Plan-Symbol verwendet.
_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_submission_pdf_mit_foto_plan_feld(client, make_mandant, make_user, make_kunde, make_vorgang):
    """Ende-zu-Ende fuer das Foto-Plan-Feature: Symbol hochladen, Feld mit
    freigegebenem Symbol anlegen, Foto hochladen + Markierung setzen, PDF
    erzeugen -- deckt photo_service.compose_foto_plan_bild und die
    Bild-Beschaffung in submission_pdf ab (dort ist die eigentliche neue
    Logik, kein reiner Rendering-Test)."""
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password="pw-123456")
    token = await login(client, admin.email, "pw-123456")
    kunde = await make_kunde(mandant=mandant)
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde)

    symbol = (
        await client.post(
            "/api/plan-symbole",
            headers=auth_headers(token),
            data={"name": "Wallbox"},
            files={"file": ("wallbox.png", _PNG_1PX, "image/png")},
        )
    ).json()

    schema = await _make_published_schema(client, token, name="E-Check")
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields",
        headers=auth_headers(token),
        json={
            "key": "verteilerfoto",
            "feld_typ": "foto_plan",
            "label": {"de": "Verteilerfoto"},
            "optionen": {"symbol_ids": [symbol["id"]]},
        },
    )
    print_view = (
        await client.post(
            f"/api/form-schemas/{schema['id']}/views",
            headers=auth_headers(token),
            json={"type": "print", "name": "Ausdruck"},
        )
    ).json()
    await client.put(
        f"/api/form-schemas/{schema['id']}/views/{print_view['id']}/layouts",
        headers=auth_headers(token),
        json=[{"field_key": "verteilerfoto", "x_mm": 0, "y_mm": 0, "breite_mm": 80, "hoehe_mm": 80}],
    )

    submission = (
        await client.post(
            "/api/form-submissions",
            headers=auth_headers(token),
            params={"vorgang_id": str(vorgang.id)},
            json={"schema_id": schema["id"]},
        )
    ).json()

    upload = (
        await client.post(
            f"/api/form-submissions/{submission['id']}/dateien",
            headers=auth_headers(token),
            params={"field_key": "verteilerfoto"},
            files={"file": ("verteiler.png", _PNG_1PX, "image/png")},
        )
    ).json()
    await client.patch(
        f"/api/form-submissions/{submission['id']}",
        headers=auth_headers(token),
        json={
            "values": {
                "verteilerfoto": {
                    "foto": {"key": upload["key"], "url": upload["url"], "content_type": upload["content_type"]},
                    "markierungen": [
                        {"art": "symbol", "symbol_id": symbol["id"], "x": 0.5, "y": 0.5, "winkel": 90},
                        {"art": "linie", "punkte": [{"x": 0.1, "y": 0.1}, {"x": 0.9, "y": 0.9}], "farbe": "#dc2626"},
                    ],
                }
            }
        },
    )

    resp = await client.get(f"/api/form-submissions/{submission['id']}/pdf", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
