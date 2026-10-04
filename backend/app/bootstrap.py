from sqlalchemy import select

from .config import get_business_config
from .db import SessionLocal
from .models import User
from .security import hash_password, verify_password


def main() -> None:
    admin = get_business_config().admin
    with SessionLocal.begin() as db:
        existing = db.scalar(select(User).where(User.email == admin.email.lower()))
        if existing:
            if not existing.is_admin or existing.deleted_at:
                raise RuntimeError('Configured admin email belongs to a non-admin account')
        else:
            existing = db.scalar(select(User).where(User.is_admin.is_(True), User.deleted_at.is_(None)))
        if existing:
            existing.email = admin.email.lower()
            existing.display_name = admin.name
            existing.max_concurrency = admin.max_concurrency
            existing.is_active = True
            if not verify_password(admin.password, existing.password_hash):
                existing.password_hash = hash_password(admin.password)
            action = 'updated'
        else:
            db.add(User(email=admin.email.lower(), display_name=admin.name,
                        password_hash=hash_password(admin.password),
                        max_concurrency=admin.max_concurrency, is_admin=True))
            action = 'created'
    print(f'Administrator {action}')


if __name__ == '__main__':
    main()
