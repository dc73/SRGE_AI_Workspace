import os

from sqlalchemy import Engine, create_engine
from sqlmodel import Session
from sqlmodel import SQLModel  # noqa: F401  (register tables on import)

from . import models  # noqa: F401

_DB_PATH = os.getenv("SRGE_DB", "srge.db")


def get_engine() -> Engine:
    return create_engine(f"sqlite:///{_DB_PATH}")


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Session:
    return Session(get_engine())
