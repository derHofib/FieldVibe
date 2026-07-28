"""Operational CLI commands, meant for production use.

Usage:
    docker compose run --rm backend python -m app.cli create-super-admin
"""
import argparse
import asyncio
import getpass
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


def main() -> None:
    parser = argparse.ArgumentParser(description="SocialCRM Betriebs-CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create-super-admin", help="Legt den ersten Plattform-Administrator an"
    )
    create_parser.add_argument("--email", required=True)
    create_parser.add_argument("--name", required=True)

    args = parser.parse_args()

    if args.command == "create-super-admin":
        asyncio.run(create_super_admin(args.email, args.name))


if __name__ == "__main__":
    main()
