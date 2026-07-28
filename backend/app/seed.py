"""Seeds two example Mandanten with users in every role.

Idempotent: safe to run multiple times, existing rows (matched by unique
email / slug) are left untouched. Run with:

    docker compose run --rm backend python -m app.seed
"""
import asyncio
import os

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import system_session
from app.models.mandant import Mandant
from app.models.user import User

SUPER_ADMIN_EMAIL = os.environ.get("SEED_SUPER_ADMIN_EMAIL", "superadmin@socialcrm.example.de")
SUPER_ADMIN_PASSWORD = os.environ.get("SEED_SUPER_ADMIN_PASSWORD", "SuperAdmin123!")
DEFAULT_PASSWORD = os.environ.get("SEED_USER_PASSWORD", "Handwerk123!")

MANDANTEN = [
    {
        "name": "Elektro Müller GmbH",
        "slug": "mueller",
        "branche": "elektro",
        "users": [
            ("admin@mueller.example.de", "mandant_admin", "Sabine Müller"),
            ("dispo@mueller.example.de", "disponent", "Jens Krause"),
            ("technik1@mueller.example.de", "techniker", "Ali Yildiz"),
            ("technik2@mueller.example.de", "techniker", "Petra Wagner"),
        ],
    },
    {
        "name": "Blitz Elektrotechnik e.K.",
        "slug": "blitz",
        "branche": "elektro",
        "users": [
            ("admin@blitz.example.de", "mandant_admin", "Markus Blitz"),
            ("dispo@blitz.example.de", "disponent", "Nadine Roth"),
            ("technik1@blitz.example.de", "techniker", "Tom Schuster"),
            ("technik2@blitz.example.de", "techniker", "Lena Fischer"),
        ],
    },
]


async def _get_or_none(session, model, **filters):
    result = await session.execute(select(model).filter_by(**filters))
    return result.scalar_one_or_none()


async def seed() -> None:
    async with system_session() as session:
        super_admin = await _get_or_none(session, User, email=SUPER_ADMIN_EMAIL)
        if super_admin is None:
            super_admin = User(
                mandant_id=None,
                email=SUPER_ADMIN_EMAIL,
                password_hash=hash_password(SUPER_ADMIN_PASSWORD),
                role="super_admin",
                name="Plattform Administrator",
            )
            session.add(super_admin)
            print(f"[seed] super_admin angelegt: {SUPER_ADMIN_EMAIL}")
        else:
            print(f"[seed] super_admin bereits vorhanden: {SUPER_ADMIN_EMAIL}")

        for mandant_data in MANDANTEN:
            mandant = await _get_or_none(session, Mandant, slug=mandant_data["slug"])
            if mandant is None:
                mandant = Mandant(
                    name=mandant_data["name"],
                    slug=mandant_data["slug"],
                    branche=mandant_data["branche"],
                    status="aktiv",
                )
                session.add(mandant)
                await session.flush()
                print(f"[seed] Mandant angelegt: {mandant.name} ({mandant.slug})")
            else:
                print(f"[seed] Mandant bereits vorhanden: {mandant.name}")

            for email, role, name in mandant_data["users"]:
                user = await _get_or_none(session, User, email=email)
                if user is None:
                    session.add(
                        User(
                            mandant_id=mandant.id,
                            email=email,
                            password_hash=hash_password(DEFAULT_PASSWORD),
                            role=role,
                            name=name,
                        )
                    )
                    print(f"[seed]   User angelegt: {email} ({role})")
                else:
                    print(f"[seed]   User bereits vorhanden: {email}")

        await session.flush()

    print("\n[seed] Fertig.")
    print(f"[seed] super_admin Passwort: {SUPER_ADMIN_PASSWORD}")
    print(f"[seed] Standard-Passwort für Mandanten-User: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
