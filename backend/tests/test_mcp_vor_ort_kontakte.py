"""MCP: vorgang_lesen/auftrag_lesen liefern Kontakte vor Ort, suchen findet sie."""
from app.db.session import system_session
from app.models.auftrag import Auftrag
from app.models.vor_ort_kontakt import VorOrtKontakt, VorOrtKontaktZuordnung
from tests.mcp_helfer import (
    ki_modul_setzen,
    mcp_client,  # noqa: F401
    mcp_laeuft,  # noqa: F401
    tool_aufrufen,
    verbinden,
)


async def test_vorgang_und_auftrag_lesen_liefern_kontakte_ohne_email(
    make_mandant, make_user, make_kunde, make_vorgang, mcp_client
):
    mandant = await make_mandant()
    await ki_modul_setzen(mandant)
    admin = await make_user(mandant=mandant, role="mandant_admin")
    kunde = await make_kunde(mandant=mandant, name="HV Mitte")
    async with system_session(grund="test") as db:
        auftrag = Auftrag(mandant_id=mandant.id, kunde_id=kunde.id, titel="Wallbox", erstellt_von=admin.id)
        db.add(auftrag)
        await db.flush()
        auftrag_id = auftrag.id
    vorgang = await make_vorgang(mandant=mandant, kunde=kunde, auftrag_id=auftrag_id)
    async with system_session(grund="test") as db:
        kontakt = VorOrtKontakt(
            mandant_id=mandant.id, kunde_id=kunde.id, name="Herr Kuhn", rolle="hausmeister", einheit="Keller",
            telefon="0221 77", email="kuhn@example.de", hinweis="Schlüssel im Büro", erreichbarkeit="ab 16 Uhr",
        )
        db.add(kontakt)
        await db.flush()
        db.add(VorOrtKontaktZuordnung(mandant_id=mandant.id, kontakt_id=kontakt.id, auftrag_id=auftrag_id, ist_hauptkontakt=True))
    t = await verbinden(mcp_client, admin)

    erwartet = {
        "name": "Herr Kuhn", "rolle": "hausmeister", "einheit": "Keller", "telefon": "0221 77",
        "hinweis": "Schlüssel im Büro", "hauptkontakt": True, "herkunft": "auftrag", "herkunft_titel": "Wallbox",
    }
    v = await tool_aufrufen(mcp_client, t["access_token"], "vorgang_lesen", {"vorgang_id": str(vorgang.id)})
    assert v["fehler"] is False and v["daten"]["vor_ort_kontakte"] == [erwartet]
    assert "vor_ort_kontakte" not in v["daten"]["vorgang"] and "kuhn@example.de" not in v["text"]
    a = await tool_aufrufen(mcp_client, t["access_token"], "auftrag_lesen", {"auftrag_id": str(auftrag_id)})
    assert a["fehler"] is False and a["daten"]["vor_ort_kontakte"] == [erwartet]

    s = await tool_aufrufen(mcp_client, t["access_token"], "suchen", {"text": "Kuhn", "typ": "vor_ort_kontakt"})
    assert [(h["titel"], h["kunde_id"]) for h in s["daten"]["treffer"]] == [("Herr Kuhn", str(kunde.id))]
