from sqlalchemy import text

from .models import SystemSetting
from .database import SessionLocal

SCHEMA_VERSION = 6

def run_v3(engine):
    """新增收据日期和收据编号字段"""
    with engine.connect() as conn:
        cursor = conn.execute(text("PRAGMA table_info(payment_records)"))
        cols = {row[1] for row in cursor.fetchall()}
        if "receipt_date" not in cols:
            conn.execute(text("ALTER TABLE payment_records ADD COLUMN receipt_date DATE"))
        if "receipt_number" not in cols:
            conn.execute(text("ALTER TABLE payment_records ADD COLUMN receipt_number VARCHAR(50)"))
        paid_col = "paid_on" if "paid_on" in cols else "paid_at"
        conn.execute(text(f"UPDATE payment_records SET receipt_date = date({paid_col}) WHERE receipt_date IS NULL"))
        conn.execute(text("UPDATE payment_records SET receipt_number = '' WHERE receipt_number IS NULL"))
        conn.commit()

def run_v4(engine):
    """将 paid_at 字段重命名为 paid_on"""
    with engine.connect() as conn:
        # 先检查 paid_at 列是否存在（兼容新库已有 paid_on）
        cursor = conn.execute(text("PRAGMA table_info(payment_records)"))
        cols = {row[1] for row in cursor.fetchall()}
        if "paid_at" in cols and "paid_on" not in cols:
            conn.execute(text("ALTER TABLE payment_records RENAME COLUMN paid_at TO paid_on"))
            conn.commit()

def run_v6(engine):
    """发票表新增冲销相关字段"""
    with engine.connect() as conn:
        cursor = conn.execute(text("PRAGMA table_info(invoices)"))
        cols = {row[1] for row in cursor.fetchall()}
        if "red_invoice_number" not in cols:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN red_invoice_number VARCHAR(100)"))
        if "cancelled_reason" not in cols:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN cancelled_reason TEXT"))
        if "cancelled_at" not in cols:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN cancelled_at DATETIME"))
        conn.commit()

def run_v5(engine):
    """将 paid_on 从 DateTime 转为 Date（去除时间部分）"""
    with engine.connect() as conn:
        cursor = conn.execute(text("SELECT 1 FROM payment_records WHERE paid_on LIKE '%:%' LIMIT 1"))
        needs_convert = cursor.fetchone() is not None
        if not needs_convert:
            return
        conn.execute(text("ALTER TABLE payment_records ADD COLUMN paid_on_new DATE"))
        conn.execute(text("UPDATE payment_records SET paid_on_new = date(paid_on)"))
        conn.execute(text("ALTER TABLE payment_records DROP COLUMN paid_on"))
        conn.execute(text("ALTER TABLE payment_records RENAME COLUMN paid_on_new TO paid_on"))
        conn.commit()

MIGRATIONS = {
    3: ("新增 receipt_date 和 receipt_number 字段", run_v3),
    4: ("将 paid_at 重命名为 paid_on", run_v4),
    5: ("将 paid_on 从 DateTime 转为 Date", run_v5),
    6: ("发票表新增冲销相关字段", run_v6),
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