"""Formulare im Office (Konzept formulare, Etappen A/B): Herkunft erstellt_via, Aggregate der Vorlagenliste,
Uebersicht ueber alle Ausfuellungen, Grenzwerte und Vorschau-PDF."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db.session import system_session
from tests.conftest import auth_headers, login

PW = "pw-123456"


async def _admin_token(client, make_mandant, make_user, name="Admin Anna"):
    mandant = await make_mandant()
    admin = await make_user(mandant=mandant, role="mandant_admin", password=PW, name=name)
    return mandant, admin, await login(client, admin.email, PW)


async def _schema(client, token, name="Wartungsprotokoll", *, publish=True, felder=()):
    schema = (await client.post("/api/form-schemas", headers=auth_headers(token), json={"name": name})).json()
    for key, typ in felder:
        r = await client.post(
            f"/api/form-schemas/{schema['id']}/fields", headers=auth_headers(token), json={"key": key, "feld_typ": typ}
        )
        assert r.status_code == 201, r.text
    if publish:
        await client.patch(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token), json={"status": "published"})
    return schema


async def _start(client, token, vorgang, schema, **extra):
    r = await client.post(
        "/api/form-submissions",
        headers=auth_headers(token),
        params={"vorgang_id": str(vorgang.id)},
        json={"schema_id": schema["id"], **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _datum_setzen(submission_id, zeitpunkt: datetime):
    async with system_session(grund="test") as session:
        await session.execute(
            text("UPDATE form_submissions SET created_at = :z WHERE id = :i"), {"z": zeitpunkt, "i": submission_id}
        )


# --- erstellt_via -------------------------------------------------------------------------------


async def test_erstellt_via_ist_app_und_nicht_per_request_setzbar(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema = (
        await client.post(
            "/api/form-schemas", headers=auth_headers(token), json={"name": "X", "erstellt_via": "ki"}
        )
    ).json()
    assert schema["erstellt_via"] == "app"
    assert (await client.get(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token))).json()["erstellt_via"] == "app"
    async with system_session(grund="test") as session:
        assert (await session.execute(text("SELECT erstellt_via FROM form_schemas WHERE id = :i"), {"i": schema["id"]})).scalar() == "app"

    await client.patch(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token), json={"status": "published"})
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    sub = await _start(client, token, vorgang, schema, erstellt_via="ki")
    assert sub["erstellt_via"] == "app"
    # PATCH auf das Schema ignoriert das Feld ebenfalls (nicht im Update-Schema).
    r = await client.patch(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token), json={"erstellt_via": "ki"})
    assert r.json()["erstellt_via"] == "app"


async def test_altbestand_ohne_erstellt_via_gilt_als_app(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema = await _schema(client, token, publish=False)
    async with system_session(grund="test") as session:
        await session.execute(text("UPDATE form_schemas SET erstellt_via = NULL WHERE id = :i"), {"i": schema["id"]})
    liste = (await client.get("/api/form-schemas", headers=auth_headers(token))).json()
    assert liste[0]["erstellt_via"] == "app"


# --- Listen-Aggregate ---------------------------------------------------------------------------


async def test_vorlagenliste_hat_aggregate(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user, name="Berta Büro")
    a = await _schema(client, token, "A-Vorlage", felder=[("f1", "text"), ("f2", "zahl"), ("f3", "ja_nein")])
    b = await _schema(client, token, "B-Vorlage", publish=False)
    for lt, pflicht in (("wartung", True), ("pruefung", False)):
        r = await client.post(
            f"/api/form-schemas/{a['id']}/zuordnungen", headers=auth_headers(token),
            json={"leistungstyp": lt, "pflicht_vor_abschluss": pflicht},
        )
        assert r.status_code == 201
    kunde = await make_kunde(mandant=mandant)
    for _ in range(2):
        await _start(client, token, await make_vorgang(mandant=mandant, kunde=kunde), a)

    liste = {s["name"]: s for s in (await client.get("/api/form-schemas", headers=auth_headers(token))).json()}
    assert liste["A-Vorlage"]["felder_anzahl"] == 3
    assert liste["A-Vorlage"]["ausgefuellt_anzahl"] == 2
    assert liste["A-Vorlage"]["leistungstypen"] == [
        {"leistungstyp": "pruefung", "pflicht_vor_abschluss": False},
        {"leistungstyp": "wartung", "pflicht_vor_abschluss": True},
    ]
    assert liste["A-Vorlage"]["erstellt_von_name"] == "Berta Büro"
    assert liste["A-Vorlage"]["updated_at"]
    assert liste["B-Vorlage"]["felder_anzahl"] == 0 and liste["B-Vorlage"]["ausgefuellt_anzahl"] == 0
    assert liste["B-Vorlage"]["leistungstypen"] == []
    detail = (await client.get(f"/api/form-schemas/{a['id']}", headers=auth_headers(token))).json()
    assert detail["felder_anzahl"] == 3 and detail["ausgefuellt_anzahl"] == 2 and len(detail["leistungstypen"]) == 2
    assert len(detail["fields"]) == 3


async def test_vorlagenliste_ohne_n_plus_1(client, make_mandant, make_user):
    """Anzahl der SQL-Statements bleibt unabhaengig von der Zahl der Vorlagen."""
    from sqlalchemy import event
    from app.db.session import engine

    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    for i in range(6):
        await _schema(client, token, f"V{i}", felder=[("f", "text")])
    anzahl = []
    listener = lambda *a, **k: anzahl.append(1)  # noqa: E731
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        r = await client.get("/api/form-schemas", headers=auth_headers(token))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert len(r.json()) == 6
    assert len(anzahl) < 20  # 6 Vorlagen: Auth/Rechte-Abfragen + 1 Liste + je 1 je Aggregat, nicht je Vorlage


# --- Uebersicht ---------------------------------------------------------------------------------


async def test_uebersicht_felder_filter_und_sortierung(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user, name="Admin Anna")
    müller = await make_kunde(mandant=mandant, name="Müller GmbH")
    meier = await make_kunde(mandant=mandant, name="Meier & Söhne")
    v1 = await make_vorgang(mandant=mandant, kunde=müller, titel="Heizung", vorgangsnummer="V-00001")
    v2 = await make_vorgang(mandant=mandant, kunde=meier, titel="Therme", vorgangsnummer="V-00002")
    wartung = await _schema(client, token, "Wartung Therme")
    pruef = await _schema(client, token, "Prüfbericht")
    s1 = await _start(client, token, v1, wartung)
    s2 = await _start(client, token, v2, pruef)
    s3 = await _start(client, token, v2, wartung)
    await client.post(f"/api/form-submissions/{s3['id']}/abschliessen", headers=auth_headers(token))
    jetzt = datetime.now(timezone.utc)
    await _datum_setzen(s1["id"], jetzt - timedelta(days=10))
    await _datum_setzen(s2["id"], jetzt - timedelta(days=5))

    async def abfrage(**params):
        r = await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token), params=params)
        assert r.status_code == 200, r.text
        return r.json()

    alle = await abfrage()
    assert alle["gesamt"] == 3
    assert [e["id"] for e in alle["eintraege"]] == [s3["id"], s2["id"], s1["id"]]  # created_at desc
    erster = alle["eintraege"][0]
    assert erster == {
        "id": s3["id"], "schema_id": wartung["id"], "schema_name": "Wartung Therme", "schema_version": 1,
        "vorgang_id": str(v2.id), "vorgangsnummer": "V-00002", "vorgang_titel": "Therme", "kunde_name": "Meier & Söhne",
        "status": "abgeschlossen", "erstellt_via": "app", "ausgefuellt_von_name": "Admin Anna", "kundensichtbar": False,
        "created_at": erster["created_at"], "abgeschlossen_am": erster["abgeschlossen_am"],
    }
    assert erster["abgeschlossen_am"] is not None

    assert {e["id"] for e in (await abfrage(status="offen"))["eintraege"]} == {s1["id"], s2["id"]}
    assert (await abfrage(status="abgeschlossen"))["gesamt"] == 1
    assert {e["id"] for e in (await abfrage(schema_id=pruef["id"]))["eintraege"]} == {s2["id"]}
    heute = date.today()
    assert {e["id"] for e in (await abfrage(von=(heute - timedelta(days=7)).isoformat()))["eintraege"]} == {s2["id"], s3["id"]}
    assert {e["id"] for e in (await abfrage(bis=(heute - timedelta(days=7)).isoformat()))["eintraege"]} == {s1["id"]}
    assert (await abfrage(von=heute.isoformat(), bis=heute.isoformat()))["gesamt"] == 1
    assert {e["id"] for e in (await abfrage(suche="v-00001"))["eintraege"]} == {s1["id"]}
    assert {e["id"] for e in (await abfrage(suche="müller"))["eintraege"]} == {s1["id"]}
    assert {e["id"] for e in (await abfrage(suche="PRÜF"))["eintraege"]} == {s2["id"]}
    assert (await abfrage(suche="%"))["gesamt"] == 0  # Platzhalter werden nicht als Muster gedeutet
    assert (await abfrage(techniker_id=str(admin.id)))["gesamt"] == 3
    assert (await abfrage(techniker_id="00000000-0000-0000-0000-000000000001"))["gesamt"] == 0

    assert (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token), params={"status": "x"})).status_code == 422
    assert (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token), params={"seite": 0})).status_code == 422


async def test_uebersicht_paginiert_je_100(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    schema = await _schema(client, token)
    async with system_session(grund="test") as session:
        await session.execute(
            text(
                """
                INSERT INTO form_submissions (mandant_id, vorgang_id, schema_id, schema_version, values, status, created_at, updated_at)
                SELECT :m, :v, :s, 1, '{}'::jsonb, 'offen', now() - (g || ' minutes')::interval, now()
                FROM generate_series(1, 105) g
                """
            ),
            {"m": mandant.id, "v": vorgang.id, "s": schema["id"]},
        )
    seite1 = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token))).json()
    seite2 = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token), params={"seite": 2})).json()
    seite3 = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token), params={"seite": 3})).json()
    assert seite1["gesamt"] == seite2["gesamt"] == 105
    assert (len(seite1["eintraege"]), len(seite2["eintraege"]), len(seite3["eintraege"])) == (100, 5, 0)
    assert not {e["id"] for e in seite1["eintraege"]} & {e["id"] for e in seite2["eintraege"]}


async def test_uebersicht_mandantentrennung_und_geloeschte_vorgaenge(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant_a, admin_a, token_a = await _admin_token(client, make_mandant, make_user)
    mandant_b, admin_b, token_b = await _admin_token(client, make_mandant, make_user)
    va = await make_vorgang(mandant=mandant_a, kunde=await make_kunde(mandant=mandant_a))
    vb = await make_vorgang(mandant=mandant_b, kunde=await make_kunde(mandant=mandant_b))
    sa = await _start(client, token_a, va, await _schema(client, token_a))
    sb = await _start(client, token_b, vb, await _schema(client, token_b))
    a = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token_a))).json()
    b = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token_b))).json()
    assert [e["id"] for e in a["eintraege"]] == [sa["id"]] and a["gesamt"] == 1
    assert [e["id"] for e in b["eintraege"]] == [sb["id"]]
    # Filter auf eine fremde Vorlage liefert nichts.
    fremd = (
        await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token_a), params={"schema_id": sb["schema_id"]})
    ).json()
    assert fremd == {"eintraege": [], "gesamt": 0}

    async with system_session(grund="test") as session:
        await session.execute(text("UPDATE vorgaenge SET geloescht_am = now() WHERE id = :i"), {"i": va.id})
    assert (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token_a))).json()["gesamt"] == 0


async def test_uebersicht_nur_zugewiesene_kunden(client, make_mandant, make_user, make_kunde, make_vorgang, make_kunde_zuweisung):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    tech = await make_user(mandant=mandant, role="techniker", password=PW, name="Tom Techniker")
    eigener_kunde = await make_kunde(mandant=mandant, name="Eigener")
    fremder_kunde = await make_kunde(mandant=mandant, name="Fremder")
    await make_kunde_zuweisung(mandant=mandant, kunde=eigener_kunde, techniker=tech)
    v_eigen = await make_vorgang(mandant=mandant, kunde=eigener_kunde)
    v_fremd = await make_vorgang(mandant=mandant, kunde=fremder_kunde)
    schema = await _schema(client, token)
    s_eigen = await _start(client, token, v_eigen, schema)
    s_fremd = await _start(client, token, v_fremd, schema)

    tech_token = await login(client, tech.email, PW)
    r = await client.get("/api/form-submissions/uebersicht", headers=auth_headers(tech_token))
    assert r.status_code == 200, r.text
    assert [e["id"] for e in r.json()["eintraege"]] == [s_eigen["id"]]
    assert r.json()["gesamt"] == 1  # Gesamtzahl verraet keine fremden Eintraege
    # Auch der Filter auf den fremden Techniker/Kunden darf nichts durchlassen.
    r = await client.get(
        "/api/form-submissions/uebersicht", headers=auth_headers(tech_token), params={"suche": "Fremder"}
    )
    assert r.json() == {"eintraege": [], "gesamt": 0}
    admin_sicht = (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token))).json()
    assert {e["id"] for e in admin_sicht["eintraege"]} == {s_eigen["id"], s_fremd["id"]}


async def test_uebersicht_braucht_recht_vorgaenge_sehen(client, make_mandant):
    from tests.mcp_helfer import PASSWORT, custom_nutzer

    mandant = await make_mandant()
    user = await custom_nutzer(mandant, "Ohne", {"kunden": ("sehen",)})
    token = await login(client, user.email, PASSWORT)
    assert (await client.get("/api/form-submissions/uebersicht", headers=auth_headers(token))).status_code == 403


# --- Grenzwerte ---------------------------------------------------------------------------------


async def test_grenzwerte_werden_validiert(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema = await _schema(client, token, publish=False)
    url = f"/api/form-schemas/{schema['id']}/fields"

    ok = await client.post(url, headers=auth_headers(token), json={"key": "co", "feld_typ": "zahl", "validation": {"warn_max": 50, "warn_min": 1.5}})
    assert ok.status_code == 201 and ok.json()["validation"] == {"warn_max": 50, "warn_min": 1.5}
    for schlecht in ({"warn_max": "50"}, {"warn_max": True}, {"warn_min": [1]}, {"warn_min": 10, "warn_max": 5}):
        r = await client.post(url, headers=auth_headers(token), json={"key": "x", "feld_typ": "zahl", "validation": schlecht})
        assert r.status_code == 400, schlecht
    r = await client.post(url, headers=auth_headers(token), json={"key": "t", "feld_typ": "text", "validation": {"warn_max": 5}})
    assert r.status_code == 400 and "Zahlenfeld" in r.json()["detail"]
    # Null = kein Grenzwert; andere validation-Keys bleiben unberuehrt.
    assert (await client.post(url, headers=auth_headers(token), json={"key": "n", "feld_typ": "zahl", "validation": {"warn_max": None, "min": 3}})).status_code == 201

    feld_id = ok.json()["id"]
    assert (await client.patch(f"{url}/{feld_id}", headers=auth_headers(token), json={"validation": {"warn_max": "viel"}})).status_code == 400
    assert (await client.patch(f"{url}/{feld_id}", headers=auth_headers(token), json={"feld_typ": "text"})).status_code == 400
    gut = await client.patch(f"{url}/{feld_id}", headers=auth_headers(token), json={"validation": {"warn_max": 80}})
    assert gut.status_code == 200 and gut.json()["validation"] == {"warn_max": 80}


async def test_grenzwert_markiert_wert_im_pdf_aber_speichern_bleibt_moeglich(client, make_mandant, make_user, make_kunde, make_vorgang):
    from app.models.form_modul import FormField
    from app.services.pdf_service import _form_antwort_text, _grenzwert_hinweis

    feld = FormField(key="co", feld_typ="zahl", label={"de": "CO"}, validation={"warn_max": 50, "warn_min": 2})
    assert _grenzwert_hinweis(feld, "51") == "über 50"
    assert _grenzwert_hinweis(feld, "50") is None
    assert _grenzwert_hinweis(feld, "1,5") == "unter 2"
    assert _grenzwert_hinweis(feld, "abc") is None and _grenzwert_hinweis(feld, "") is None
    assert _form_antwort_text(feld, "60") == "60 (über 50)"
    assert _form_antwort_text(FormField(key="t", feld_typ="text", label={}, validation={"warn_max": 1}), "60") == "60"

    # Ende-zu-Ende: Wert ueber Grenzwert speichern geht, PDF wird erzeugt.
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema = await _schema(client, token, publish=False)
    await client.post(
        f"/api/form-schemas/{schema['id']}/fields", headers=auth_headers(token),
        json={"key": "co", "feld_typ": "zahl", "label": {"de": "CO"}, "validation": {"warn_max": 50}},
    )
    view = (await client.post(f"/api/form-schemas/{schema['id']}/views", headers=auth_headers(token), json={"type": "print", "name": "Druck"})).json()
    await client.put(
        f"/api/form-schemas/{schema['id']}/views/{view['id']}/layouts", headers=auth_headers(token),
        json=[{"field_key": "co", "x_mm": 0, "y_mm": 0}],
    )
    await client.patch(f"/api/form-schemas/{schema['id']}", headers=auth_headers(token), json={"status": "published"})
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    sub = await _start(client, token, vorgang, schema)
    r = await client.patch(f"/api/form-submissions/{sub['id']}", headers=auth_headers(token), json={"values": {"co": "75"}})
    assert r.status_code == 200 and r.json()["values"]["co"] == "75"
    pdf = await client.get(f"/api/form-submissions/{sub['id']}/pdf", headers=auth_headers(token))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


# --- Vorschau-PDF -------------------------------------------------------------------------------


async def _schema_mit_druckansicht(client, token):
    schema = await _schema(client, token, "Vorschau-Vorlage", publish=False)
    sid = schema["id"]
    felder = [
        ("kunde", "text", {"datenquelle": "kunde.name"}),
        ("notiz", "text", {}),
        ("messwert", "zahl", {"validation": {"warn_max": 10}}),
        ("ok", "ja_nein", {}),
    ]
    for key, typ, extra in felder:
        r = await client.post(
            f"/api/form-schemas/{sid}/fields", headers=auth_headers(token),
            json={"key": key, "feld_typ": typ, "label": {"de": key.capitalize()}, **extra},
        )
        assert r.status_code == 201, r.text
    view = (await client.post(f"/api/form-schemas/{sid}/views", headers=auth_headers(token), json={"type": "print", "name": "Druck"})).json()
    layouts = [{"field_key": k, "x_mm": 0, "y_mm": 10 * i} for i, (k, _, _) in enumerate(felder)]
    r = await client.put(f"/api/form-schemas/{sid}/views/{view['id']}/layouts", headers=auth_headers(token), json=layouts)
    assert r.status_code == 200, r.text
    await client.patch(f"/api/form-schemas/{sid}", headers=auth_headers(token), json={"status": "published"})
    return schema, view


async def test_vorschau_pdf_ohne_submission_zeigt_platzhalter(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema, view = await _schema_mit_druckansicht(client, token)
    r = await client.get(f"/api/form-schemas/{schema['id']}/views/{view['id']}/vorschau-pdf", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "Vorschau-" in r.headers["content-disposition"]
    # Nichts wurde angelegt.
    async with system_session(grund="test") as session:
        assert (await session.execute(text("SELECT count(*) FROM form_submissions"))).scalar() == 0


async def test_platzhalter_werte_je_feldtyp():
    from app.models.form_modul import FormField, FormGroup
    from app.services.form_modul_service import platzhalter_werte

    def f(key, typ, **kw):
        return FormField(key=key, feld_typ=typ, label={}, optionen=kw.pop("optionen", {}), datenquelle=kw.pop("datenquelle", None), group_key=kw.pop("group_key", None))

    felder = [
        f("a", "text"), f("b", "zahl"), f("c", "ja_nein"), f("d", "dropdown", optionen={"werte": ["Eins", "Zwei"]}),
        f("e", "mehrfachauswahl", optionen={"werte": ["X", "Y", "Z"]}), f("g", "foto"), f("h", "text", datenquelle="kunde.name"),
        f("i", "datum"), f("j", "text", group_key="liste"),
    ]
    gruppen = [FormGroup(key="liste", label={}, repeatable=True)]
    w = platzhalter_werte(felder, gruppen)
    assert w["a"] == "Beispieltext" and w["b"] == "42" and w["c"] is True and w["d"] == "Eins" and w["e"] == ["X", "Y"]
    assert "g" not in w  # Bilder bleiben leer
    assert w["h"] == "(automatisch)"
    assert w["i"] == date.today().isoformat()
    assert w["liste"] == [{"j": "Beispieltext"}, {"j": "Beispieltext"}]
    assert "j" not in w


async def test_vorschau_pdf_mit_submission_und_fremdem_schema(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema, view = await _schema_mit_druckansicht(client, token)
    andere = await _schema(client, token, "Andere")
    vorgang = await make_vorgang(mandant=mandant, kunde=await make_kunde(mandant=mandant))
    sub = await _start(client, token, vorgang, schema)
    await client.patch(f"/api/form-submissions/{sub['id']}", headers=auth_headers(token), json={"values": {"messwert": "99"}})
    url = f"/api/form-schemas/{schema['id']}/views/{view['id']}/vorschau-pdf"
    r = await client.get(url, headers=auth_headers(token), params={"submission_id": sub["id"]})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    # Ausfuellung gehoert zu anderem Schema.
    sub2 = await _start(client, token, vorgang, andere)
    assert (await client.get(url, headers=auth_headers(token), params={"submission_id": sub2["id"]})).status_code == 404
    # Unbekannte Ausfuellung / unbekannte View.
    assert (await client.get(url, headers=auth_headers(token), params={"submission_id": "00000000-0000-0000-0000-000000000001"})).status_code == 404
    assert (
        await client.get(f"/api/form-schemas/{schema['id']}/views/00000000-0000-0000-0000-000000000001/vorschau-pdf", headers=auth_headers(token))
    ).status_code == 404


async def test_vorschau_pdf_fremder_mandant_404(client, make_mandant, make_user, make_kunde, make_vorgang):
    mandant_a, admin_a, token_a = await _admin_token(client, make_mandant, make_user)
    mandant_b, admin_b, token_b = await _admin_token(client, make_mandant, make_user)
    schema, view = await _schema_mit_druckansicht(client, token_a)
    vorgang = await make_vorgang(mandant=mandant_a, kunde=await make_kunde(mandant=mandant_a))
    sub = await _start(client, token_a, vorgang, schema)
    url = f"/api/form-schemas/{schema['id']}/views/{view['id']}/vorschau-pdf"
    assert (await client.get(url, headers=auth_headers(token_b))).status_code == 404
    assert (await client.get(url, headers=auth_headers(token_b), params={"submission_id": sub["id"]})).status_code == 404


async def test_vorschau_pdf_braucht_recht_formulare_sehen(client, make_mandant, make_user):
    mandant, admin, token = await _admin_token(client, make_mandant, make_user)
    schema, view = await _schema_mit_druckansicht(client, token)
    tech = await make_user(mandant=mandant, role="techniker", password=PW)
    tech_token = await login(client, tech.email, PW)
    r = await client.get(f"/api/form-schemas/{schema['id']}/views/{view['id']}/vorschau-pdf", headers=auth_headers(tech_token))
    assert r.status_code == 403
