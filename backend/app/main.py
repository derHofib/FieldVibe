from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import (
    anlagen,
    audit_log,
    auth,
    feed,
    impersonation,
    kunden,
    mandanten,
    notifications,
    search,
    stories,
    stream,
    tags,
    users,
    vertraege,
    vorgaenge,
    vorgang_events,
    zeiterfassung,
)
from app.core.config import get_settings
from app.db.session import engine
from app.services.storage_service import ensure_bucket

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_bucket()
    yield


app = FastAPI(
    title="SocialCRM API",
    description=(
        "Mandantenfähiges Auftragsmanagement- und CRM-System für den "
        "Elektro-Handwerksbetrieb – Phase 4: Feld-Tauglichkeit."
    ),
    version="0.4.0",
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
app.include_router(mandanten.router)
app.include_router(users.router)
app.include_router(impersonation.router)
app.include_router(audit_log.router)
app.include_router(kunden.router)
app.include_router(anlagen.router)
app.include_router(vertraege.router)
app.include_router(vorgaenge.router)
app.include_router(vorgang_events.router)
app.include_router(tags.router)
app.include_router(feed.router)
app.include_router(stories.router)
app.include_router(search.router)
app.include_router(notifications.router)
app.include_router(stream.router)
app.include_router(zeiterfassung.router)


@app.get("/healthz")
async def healthz() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await ensure_bucket()
    return {"status": "ok"}
