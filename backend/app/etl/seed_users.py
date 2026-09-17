"""Seed demo user accounts so the app is usable immediately after `docker compose up`."""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import models as m

DEMO_USERS = [
    dict(email="admin@chainsight.io", password="Admin123!", full_name="Alex Admin", role="admin"),
    dict(email="analyst@chainsight.io", password="Analyst123!", full_name="Jamie Analyst", role="analyst"),
    dict(email="viewer@chainsight.io", password="Viewer123!", full_name="Sam Viewer", role="viewer"),
]


def run():
    session = SessionLocal()
    try:
        for u in DEMO_USERS:
            existing = session.query(m.User).filter(m.User.email == u["email"]).first()
            if existing:
                continue
            session.add(m.User(
                email=u["email"], hashed_password=hash_password(u["password"]),
                full_name=u["full_name"], role=u["role"],
            ))
        session.commit()
        print("[seed_users] Demo users ensured: admin@chainsight.io / analyst@chainsight.io / viewer@chainsight.io (see README for passwords)")
    finally:
        session.close()


if __name__ == "__main__":
    run()
