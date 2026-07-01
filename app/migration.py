from .models import SystemSetting
from .database import SessionLocal

SCHEMA_VERSION = 1

MIGRATIONS = {
}

def get_current_version(db):
    setting = db.query(SystemSetting).filter_by(key='db_schema_version').first()
    if setting:
        return int(setting.value)
    return 0

def set_current_version(db, version):
    setting = db.query(SystemSetting).filter_by(key='db_schema_version').first()
    if setting:
        setting.value = str(version)
    else:
        db.add(SystemSetting(key='db_schema_version', value=str(version)))
    db.commit()

def run_migrations(engine):
    db = SessionLocal()
    try:
        current = get_current_version(db)
        if current >= SCHEMA_VERSION:
            return

        for v in range(current + 1, SCHEMA_VERSION + 1):
            if v in MIGRATIONS:
                desc, fn = MIGRATIONS[v]
                print(f"[迁移] 正在执行 v{v}: {desc}")
                fn(engine)
            set_current_version(db, v)
            print(f"[迁移] schema 已升级到 v{v}")
    finally:
        db.close()