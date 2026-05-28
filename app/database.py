from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()


def database_url() -> str:
    configured_url = settings.effective_database_url
    if configured_url.startswith("postgres://"):
        return configured_url.replace("postgres://", "postgresql+psycopg://", 1)
    if configured_url.startswith("postgresql://"):
        return configured_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not configured_url.startswith("sqlite:///./"):
        return configured_url
    relative_path = configured_url.removeprefix("sqlite:///./")
    absolute_path = Path(__file__).resolve().parent.parent / relative_path
    return f"sqlite:///{absolute_path.as_posix()}"


resolved_database_url = database_url()
engine_options = {"pool_pre_ping": True}
if make_url(resolved_database_url).drivername.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(resolved_database_url, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
