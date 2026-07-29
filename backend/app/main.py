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
)
from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()

app = FastAPI(
    title="SocialCRM API",
    description=(
        "Mandantenfähiges Auftragsmanagement- und CRM-System für den "
        "Elektro-Handwerksbetrieb – Phase 3: Social-UX."
    ),
    version="0.3.0",
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


@app.get("/healthz")
async def healthz() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
