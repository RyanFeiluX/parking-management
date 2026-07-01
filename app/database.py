import os
import json
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from ._path import get_db_path, get_config_path, ensure_user_data_dir

def _get_database_url():
    config_path = get_config_path()

    if env_url := os.environ.get('PARKING_DB_URL'):
        return env_url

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if cfg.get('db_url'):
                return cfg['db_url']
            if cfg.get('db_path'):
                return f"sqlite:///{cfg['db_path']}"
        except (json.JSONDecodeError, IOError):
            pass

    ensure_user_data_dir()
    return f"sqlite:///{get_db_path()}"

SQLALCHEMY_DATABASE_URL = _get_database_url()

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()