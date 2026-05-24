from app.database import SessionLocal, engine
from app.models import Base, User, SystemSetting
from app.auth import get_password_hash
from datetime import datetime

# Create tables if not exist
Base.metadata.create_all(bind=engine)

db = SessionLocal()

def init_default_settings(db):
    settings = [
        {"key": "grace_period_days", "value": "15", "description": "车辆过期宽限期(天)"},
        {"key": "api_token", "value": "", "description": "外部API访问令牌"},
        {"key": "company_name", "value": "小区停车管理系统", "description": "系统标题"},
        {"key": "temp_parking_rules", "value": '{"free_minutes": 30, "daily_cap": 20.00, "tiers": [{"from_hours": 0, "to_hours": 1, "fee": 0}, {"from_hours": 1, "to_hours": 2, "fee": 5}, {"from_hours": 2, "to_hours": 12, "fee": 10}, {"from_hours": 12, "to_hours": 24, "fee": 20}], "overflow": "daily_reset"}', "description": "临时停车费率规则"}
    ]
    for s in settings:
        existing = db.query(SystemSetting).filter_by(key=s["key"]).first()
        if not existing:
            db.add(SystemSetting(**s))
    db.commit()

# Check if we have users
user_count = db.query(User).count()
print(f"当前用户数: {user_count}")

if user_count > 0:
    # Update first user password
    user = db.query(User).first()
    print(f"更新用户密码: {user.username}")
    user.password_hash = get_password_hash("password123")
    db.commit()
    print("密码已重置为: password123")
else:
    # Create new user
    print("创建新用户...")
    user = User(
        username="admin",
        display_name="管理员",
        password_hash=get_password_hash("password123"),
        role="super_admin",
        is_active=True,
        created_at=datetime.now()
    )
    db.add(user)
    init_default_settings(db)
    db.commit()
    print("用户创建成功!")
    print("用户名: admin")
    print("密码: password123")

db.close()
