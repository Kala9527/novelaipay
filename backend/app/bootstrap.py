from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import User
from .security import hash_password


def main() -> None:
    settings = get_settings()
    if len(settings.admin_password) < 12:
        raise ValueError('ADMIN_PASSWORD must contain at least 12 characters')
    with SessionLocal.begin() as db:
        existing = db.scalar(select(User).where(User.email == settings.admin_email.lower()))
        if existing:
            print('Administrator already exists')
            return
        db.add(User(email=settings.admin_email.lower(),
                    password_hash=hash_password(settings.admin_password), is_admin=True))
    print('Administrator created')


if __name__ == '__main__':
    main()
