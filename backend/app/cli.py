"""Operational CLI commands, meant for production use.

Usage:
    docker compose run --rm backend python -m app.cli create-super-admin
"""
import argparse
import asyncio
import getpass
import hashlib
import secrets
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import system_session
from app.models.user import User


async def create_super_admin(email: str, name: str) -> None:
    async with system_session() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none() is not None:
            print(f"Fehler: Es existiert bereits ein Account mit E-Mail {email}", file=sys.stderr)
            raise SystemExit(1)

        password = getpass.getpass("Passwort: ")
        confirm = getpass.getpass("Passwort bestätigen: ")
        if password != confirm:
            print("Fehler: Passwörter stimmen nicht überein", file=sys.stderr)
            raise SystemExit(1)
        if len(password) < 12:
            print("Fehler: Passwort muss mindestens 12 Zeichen lang sein", file=sys.stderr)
            raise SystemExit(1)

        session.add(
            User(
                mandant_id=None,
                email=email,
                password_hash=hash_password(password),
                role="super_admin",
                name=name,
            )
        )
    print(f"super_admin '{email}' wurde angelegt.")


def fehlerbericht_token() -> None:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    print("Neues Service-Token für die Fehlerbericht-API erzeugt.\n")
    print(f"Token (nur in der Claude-Umgebungsvariable, nie in .env/Git):\n  FIELDVIBE_BUGREPORT_TOKEN={token}\n")
    print(f"Hash (in die .env des Servers):\n  FIELDVIBE_FEHLERBERICHT_TOKEN_HASH={token_hash}\n")
    print("Das Token wird nicht gespeichert und lässt sich nicht aus dem Hash rekonstruieren.")


def main() -> None:
    parser = argparse.ArgumentParser(description="FieldVibe Betriebs-CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create-super-admin", help="Legt den ersten Plattform-Administrator an"
    )
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--name", required=True)

    subparsers.add_parser(
        "fehlerbericht-token", help="Erzeugt ein Service-Token (+ Hash) für die Fehlerbericht-API"
    )

    args = parser.parse_args()

    if args.command == "fehlerbericht-token":
        fehlerbericht_token()
    elif args.command == "create-super-admin":
        asyncio.run(create_super_admin(args.email, args.name))


if __name__ == "__main__":
    main()
