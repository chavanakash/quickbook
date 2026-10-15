import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

logger = logging.getLogger(__name__)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(retries: int = 10, delay: float = 3.0) -> None:
    """Create tables, retrying while the database is still starting up.

    In docker-compose / Kubernetes the app container can start before Postgres
    accepts connections, so we wait instead of crashing immediately. With several
    replicas starting together, one may also lose the race to create a table;
    the retry then finds the table already there.
    """
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except SQLAlchemyError:
            if attempt == retries:
                raise
            logger.warning("database not ready (attempt %s/%s), retrying in %ss", attempt, retries, delay)
            time.sleep(delay)
