"""Create demo accounts (one per role) with random passwords, printed once.

Usage, from backend/ with DATABASE_URL configured and migrations applied (python -m alembic upgrade head):
    python seed_demo_users.py            # create missing demo accounts
    python seed_demo_users.py --reset    # also give existing demo accounts new passwords
Passwords are random and shown only in this output; store them in your password manager.
Disable the demo accounts (Operations dashboard → Team & roles) before sharing the server externally.
"""
import argparse
import secrets
import sys

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionLocal
from app.models.platform import User

DEMO_USERS = [
    ("demo.ops", "Demo Operations Manager", ["ops_manager"]),
    ("demo.qclead", "Demo QC Lead", ["qc_lead"]),
    ("demo.qc", "Demo QC Analyst", ["qc_analyst"]),
    ("demo.reviewer1", "Demo Reviewer 1", ["reviewer"]),
    ("demo.reviewer2", "Demo Reviewer 2", ["reviewer"]),
    ("demo.field", "Demo Field Verifier", ["field_verifier"]),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="give existing demo accounts new passwords")
    args = parser.parse_args()
    if SessionLocal is None:
        sys.exit("DATABASE_URL is not configured.")
    rows = []
    with SessionLocal() as db:
        for username, name, roles in DEMO_USERS:
            user = db.scalar(select(User).where(User.username == username))
            if user and not args.reset:
                rows.append((username, roles, "(exists — unchanged)"))
                continue
            password = secrets.token_urlsafe(12)
            if user:
                user.password_hash, user.active = hash_password(password), True
            else:
                db.add(User(username=username, display_name=name, password_hash=hash_password(password), roles=roles, aois=[]))
            rows.append((username, roles, password))
        db.commit()
    print(f"{'Username':<16} {'Role':<16} Password")
    for username, roles, password in rows:
        print(f"{username:<16} {roles[0]:<16} {password}")


if __name__ == "__main__":
    main()
