from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import (
    account_typen,
    angebote,
    anlagen,
    anlagen_feld_definitionen,
    audit_log,
    auth,
    bestellungen,
    dauerauftraege,
    fahrzeug_zuweisungen,
    feed,
    gespeicherte_filter,
    highlights,
    impersonation,
    insights,
    integrationen,
    inventurzyklen,
    kunden,
    kundenportal,
    kundenportal_auth,
    lieferanten,
    maengel,
    mandant_einstellungen,
    mandanten,
    material,
    material_bedarfe,
    notifications,
    papierkorb,
    pruefmittel,
    pruefzyklen,
    rechnungen,
    search,
    standorte,
    stories,
    stream,
    tags,
    termine,
    users,
    vertraege,
    vorgaenge,
    vorgang_anfragen,
    vorgang_events,
    zeiterfassung,
    zuweisungen,
)
from app.core.config import get_settings
from app.db.session import engine
from app.services.scheduler_service import get_last_scheduler_run
from app.services.storage_service import ensure_bucket

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_bucket()
    yield


app = FastAPI(
    title="FieldVibe API",
    description=(
        "Mandantenfähiges Auftragsmanagement- und CRM-System für den "
        "Elektro-Handwerksbetrieb – Phase 7: Ausbau."
    ),
    version="0.7.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(account_typen.router)
app.include_router(angebote.router)
app.include_router(mandanten.router)
app.include_router(users.router)
app.include_router(impersonation.router)
app.include_router(audit_log.router)
app.include_router(kunden.router)
app.include_router(anlagen.router)
app.include_router(anlagen_feld_definitionen.router)
app.include_router(standorte.router)
app.include_router(dauerauftraege.router)
app.include_router(vertraege.router)
app.include_router(vorgaenge.router)
app.include_router(vorgang_anfragen.router)
app.include_router(vorgang_events.router)
app.include_router(tags.router)
app.include_router(feed.router)
app.include_router(gespeicherte_filter.router)
app.include_router(stories.router)
app.include_router(search.router)
app.include_router(notifications.router)
app.include_router(stream.router)
app.include_router(zeiterfassung.router)
app.include_router(termine.router)
app.include_router(pruefzyklen.router)
app.include_router(pruefmittel.router)
app.include_router(maengel.router)
app.include_router(rechnungen.router)
app.include_router(kundenportal_auth.router)
app.include_router(kundenportal.router)
app.include_router(highlights.router)
app.include_router(material.router)
app.include_router(lieferanten.router)
app.include_router(material_bedarfe.router)
app.include_router(bestellungen.router)
app.include_router(insights.router)
app.include_router(integrationen.router)
app.include_router(mandant_einstellungen.router)
app.include_router(zuweisungen.router)
app.include_router(fahrzeug_zuweisungen.router)
app.include_router(inventurzyklen.router)
app.include_router(papierkorb.router)


@app.get("/healthz")
async def healthz() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await ensure_bucket()
    letzter_scheduler_lauf = await get_last_scheduler_run()
    return {
        "status": "ok",
        "scheduler_letzter_lauf": letzter_scheduler_lauf.isoformat()
        if letzter_scheduler_lauf
        else None,
    }
