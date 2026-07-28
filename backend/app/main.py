from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import audit_log, auth, impersonation, mandanten, users
from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()

app = FastAPI(
    title="SocialCRM API",
    description=(
        "Mandantenfähiges Auftragsmanagement- und CRM-System für den "
        "Elektro-Handwerksbetrieb – Phase 1: Fundament."
    ),
    version="0.1.0",
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


@app.get("/healthz")
async def healthz() -> dict:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
