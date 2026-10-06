from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from . import models  # noqa: F401
from .db import Base, engine


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    if not inspect(engine).get_table_names():
        Base.metadata.create_all(engine)
        command.stamp(config, 'head')
    else:
        command.upgrade(config, 'head')


if __name__ == '__main__':
    main()
