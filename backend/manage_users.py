"""Create or reset platform users from the command line (bootstraps the first Operations Manager).

Usage, from backend/ with DATABASE_URL configured:
    python manage_users.py create --username ops.lead --name "Ops Lead" --roles ops_manager qc_lead
    python manage_users.py reset-password --username ops.lead
Passwords are prompted for and never echoed or accepted on the command line.
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app.auth import MIN_PASSWORD_LENGTH, ROLES, hash_password
from app.db import SessionLocal
from app.models.platform import User
from app.services.customer_import import AOIS


def prompt_password():
    first = getpass.getpass("Password: ")
    if len(first) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.")
    if getpass.getpass("Repeat password: ") != first:
        sys.exit("Passwords did not match.")
    return first


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--username", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--roles", nargs="+", required=True, choices=list(ROLES))
    create.add_argument("--aois", nargs="*", default=[], choices=list(AOIS))
    reset = sub.add_parser("reset-password")
    reset.add_argument("--username", required=True)
    args = parser.parse_args()
    if SessionLocal is None:
        sys.exit("DATABASE_URL is not configured.")
    with SessionLocal() as db:
        username = args.username.strip().lower()
        user = db.scalar(select(User).where(User.username == username))
        if args.command == "create":
            if user:
                sys.exit(f"User {username} already exists.")
            db.add(User(username=username, display_name=args.name, password_hash=hash_password(prompt_password()),
                        roles=sorted(set(args.roles)), aois=sorted(set(args.aois))))
        else:
            if not user:
                sys.exit(f"User {username} not found.")
            user.password_hash = hash_password(prompt_password())
        db.commit()
    print(f"{args.command}: {username} done.")


if __name__ == "__main__":
    main()
