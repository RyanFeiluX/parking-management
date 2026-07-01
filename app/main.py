import os
from fastapi import FastAPI, Depends, Request, HTTPException, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional
import json

from .database import engine, get_db, Base
from .models import User, SystemSetting
from .auth import set_session_cookie, clear_session_cookie, verify_password, get_password_hash, decode_session_data, create_session_data
from .deps import get_user, require_role
from .jinja import templates
from ._path import get_data_dir

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(get_data_dir(), "app/static")), name="static")

@app.get("/favicon.ico")
async def favicon():
    return RedirectResponse(url="/static/favicon.svg")

def init_default_settings(db: Session):
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

Base.metadata.create_all(bind=engine)

from .database import SessionLocal
_db = SessionLocal()
if _db.query(User).count() == 0:
    admin_user = User(
        username="admin",
        display_name="超级管理员",
        password_hash=get_password_hash("password123"),
        role="super_admin",
        is_active=True,
        created_at=datetime.now()
    )
    _db.add(admin_user)
    init_default_settings(_db)
    _db.commit()
    print("[初始化] 默认超级管理员已创建: admin / password123")
_db.close()

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    request.state.db = next(get_db())
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        if type(e).__name__ in ('EndOfStream', 'ExceptionGroup'):
            raise
        print(f"\n!!! EXCEPTION OCCURRED !!!")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db = getattr(request.state, "db", None)
        if db:
            db.close()

@app.middleware("http")
async def refresh_session_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as e:
        if type(e).__name__ in ('EndOfStream', 'ExceptionGroup'):
            raise
        raise
    else:
        session_cookie = request.cookies.get("parking_session")
        if session_cookie:
            has_session_cookie = any(
                k.lower() == b'set-cookie' and v.startswith(b'parking_session=')
                for k, v in response.raw_headers
            )
            if not has_session_cookie:
                user_data = decode_session_data(session_cookie)
                if user_data:
                    new_session = create_session_data(
                        user_data["user_id"],
                        user_data["username"],
                        user_data["role"]
                    )
                    response.set_cookie(
                        key="parking_session",
                        value=new_session,
                        httponly=True,
                        samesite="lax",
                        secure=False
                    )
        return response

@app.get("/")
async def index(request: Request):
    db = request.state.db
    user_count = db.query(User).count()
    
    if user_count == 0:
        return templates.TemplateResponse("auth/setup.html", {"request": request})
    
    current_user = await get_user(request)
    if not current_user:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    
    from .models import Resident, Vehicle, PaymentRecord
    from .utils import get_vehicle_payment_status
    
    today = date.today()
    current_month = today.replace(day=1)
    
    free_count = 0
    contract_count = 0
    temp_count = 0
    expired_count = 0
    
    vehicles = db.query(Vehicle).all()
    for v in vehicles:
        status = get_vehicle_payment_status(v, db)
        if status["status"] == "免费":
            free_count += 1
        elif status["status"] == "合约":
            contract_count += 1
        elif status["status"] == "临时":
            temp_count += 1
        elif status["status"] == "过期":
            expired_count += 1
    
    resident_count = db.query(Resident).count()
    vehicle_count = len(vehicles)
    
    monthly_payment = db.query(PaymentRecord).filter(
        PaymentRecord.paid_at >= current_month
    ).with_entities(PaymentRecord.amount).all()
    monthly_total = sum(p[0] for p in monthly_payment)
    
    yearly_payment = db.query(PaymentRecord).filter(
        PaymentRecord.paid_at >= today.replace(month=1, day=1)
    ).with_entities(PaymentRecord.amount).all()
    yearly_total = sum(p[0] for p in yearly_payment)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "current_user": current_user,
        "resident_count": resident_count,
        "vehicle_count": vehicle_count,
        "free_count": free_count,
        "contract_count": contract_count,
        "temp_count": temp_count,
        "expired_count": expired_count,
        "monthly_total": monthly_total,
        "yearly_total": yearly_total
    })

@app.get("/setup")
async def setup_page(request: Request):
    db = request.state.db
    user_count = db.query(User).count()
    if user_count > 0:
        return templates.TemplateResponse("auth/login.html", {"request": request})
    return templates.TemplateResponse("auth/setup.html", {"request": request})

@app.post("/setup")
async def setup(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    display_name = form_data.get("display_name")
    password = form_data.get("password")
    confirm_password = form_data.get("confirm_password")
    
    if password != confirm_password:
        return templates.TemplateResponse("auth/setup.html", {"request": request, "error": "两次输入的密码不一致"})
    
    if len(password) < 6:
        return templates.TemplateResponse("auth/setup.html", {"request": request, "error": "密码长度至少6位"})
    
    db = request.state.db
    existing = db.query(User).filter_by(username=username).first()
    if existing:
        return templates.TemplateResponse("auth/setup.html", {"request": request, "error": "用户名已存在"})
    
    user = User(
        username=username,
        display_name=display_name,
        password_hash=get_password_hash(password),
        role="super_admin"
    )
    db.add(user)
    init_default_settings(db)
    db.commit()
    
    response = templates.TemplateResponse("auth/login.html", {"request": request, "success": "超级管理员账号创建成功，请登录"})
    return response

@app.get("/login")
async def login_page(request: Request):
    db = request.state.db
    user_count = db.query(User).count()
    if user_count == 0:
        return templates.TemplateResponse("auth/setup.html", {"request": request})
    return templates.TemplateResponse("auth/login.html", {"request": request})

@app.post("/login")
async def login(request: Request):
    form_data = await request.form()
    username = form_data.get("username")
    password = form_data.get("password")
    
    db = request.state.db
    user = db.query(User).filter_by(username=username).first()
    
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "用户名或密码错误"})
    
    if not user.is_active:
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "账号已被停用"})
    
    user.last_login = datetime.now()
    db.commit()
    
    response = RedirectResponse(url="/", status_code=303)
    return set_session_cookie(response, user.id, user.username, user.role)

@app.post("/logout")
async def logout(request: Request):
    response = templates.TemplateResponse("auth/login.html", {"request": request})
    return clear_session_cookie(response)

@app.get("/change-password")
async def change_password_page(request: Request, user: dict = Depends(require_role("super_admin", "admin", "operator"))):
    return templates.TemplateResponse("auth/change_password.html", {"request": request, "current_user": user})

@app.post("/change-password")
async def change_password(request: Request, user: dict = Depends(require_role("super_admin", "admin", "operator"))):
    form_data = await request.form()
    old_password = form_data.get("old_password")
    new_password = form_data.get("new_password")
    confirm_password = form_data.get("confirm_password")
    
    db = request.state.db
    db_user = db.query(User).filter_by(id=user["user_id"]).first()
    
    if not verify_password(old_password, db_user.password_hash):
        return templates.TemplateResponse("auth/change_password.html", {"request": request, "current_user": user, "error": "原密码错误"})
    
    if new_password != confirm_password:
        return templates.TemplateResponse("auth/change_password.html", {"request": request, "current_user": user, "error": "两次输入的密码不一致"})
    
    if len(new_password) < 6:
        return templates.TemplateResponse("auth/change_password.html", {"request": request, "current_user": user, "error": "密码长度至少6位"})
    
    db_user.password_hash = get_password_hash(new_password)
    db.commit()
    
    return templates.TemplateResponse("auth/change_password.html", {"request": request, "current_user": user, "success": "密码修改成功"})

from .routers import users, residents, vehicles, payments, fee_tiers, discounts, stats, logs, settings, api, invoices

app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(residents.router, prefix="/residents", tags=["residents"])
app.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
app.include_router(payments.router, prefix="/payments", tags=["payments"])
app.include_router(fee_tiers.router, prefix="/fee-tiers", tags=["fee_tiers"])
app.include_router(discounts.router, prefix="/discounts", tags=["discounts"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(settings.router, prefix="/settings", tags=["settings"])
app.include_router(api.router, prefix="/api", tags=["api"])
app.include_router(invoices.router, prefix="/invoices", tags=["invoices"])