from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import User, OperationLog
from ..auth import get_password_hash, verify_password
from ..deps import require_role

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def log_operation(db: Session, user_id: int, action_type: str, target: str, detail: str, ip_address: str = None):
    if ip_address is None:
        ip_address = "unknown"
    log = OperationLog(
        user_id=user_id,
        action_type=action_type,
        target=target,
        detail=detail,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()

@router.get("/")
async def list_users(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    users = db.query(User).all()
    return templates.TemplateResponse("users/list.html", {"request": request, "current_user": user, "users": users})

@router.get("/add")
async def add_user_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    return templates.TemplateResponse("users/form.html", {"request": request, "current_user": user, "roles": ["operator", "admin", "super_admin"]})

@router.post("/add")
async def add_user(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    username = form_data.get("username")
    display_name = form_data.get("display_name")
    password = form_data.get("password")
    confirm_password = form_data.get("confirm_password")
    role = form_data.get("role", "operator")
    
    db = request.state.db
    
    if password != confirm_password:
        return templates.TemplateResponse("users/form.html", {"request": request, "current_user": user, "roles": ["operator", "admin", "super_admin"], "error": "两次输入的密码不一致"})
    
    existing = db.query(User).filter_by(username=username).first()
    if existing:
        return templates.TemplateResponse("users/form.html", {"request": request, "current_user": user, "roles": ["operator", "admin", "super_admin"], "error": "用户名已存在"})
    
    new_user = User(
        username=username,
        display_name=display_name,
        password_hash=get_password_hash(password),
        role=role
    )
    db.add(new_user)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "create_user", f"用户 {username}", f"创建用户: {display_name} ({role})", client_host)
    
    return templates.TemplateResponse("users/list.html", {"request": request, "current_user": user, "users": db.query(User).all(), "success": "用户创建成功"})

@router.get("/{user_id}/edit")
async def edit_user_page(request: Request, user_id: int, current_user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "用户不存在"})
    return templates.TemplateResponse("users/form.html", {"request": request, "current_user": current_user, "user": user, "roles": ["operator", "admin", "super_admin"]})

@router.post("/{user_id}/edit")
async def edit_user(request: Request, user_id: int, current_user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    display_name = form_data.get("display_name")
    role = form_data.get("role")
    password = form_data.get("password")
    
    db = request.state.db
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "用户不存在"})
    
    user.display_name = display_name
    user.role = role
    
    if password:
        confirm_password = form_data.get("confirm_password")
        if password != confirm_password:
            return templates.TemplateResponse("users/form.html", {"request": request, "current_user": current_user, "user": user, "roles": ["operator", "admin", "super_admin"], "error": "两次输入的密码不一致"})
        user.password_hash = get_password_hash(password)
    
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, current_user["user_id"], "update_user", f"用户 {user.username}", f"修改用户: {display_name} ({role})", client_host)
    
    return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "success": "用户修改成功"})

@router.post("/{user_id}/toggle")
async def toggle_user(request: Request, user_id: int, current_user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "用户不存在"})
    
    if user.id == current_user["user_id"]:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "不能停用自己"})
    
    user.is_active = not user.is_active
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, current_user["user_id"], "update_user", f"用户 {user.username}", f"{'启用' if user.is_active else '停用'}用户", client_host)
    
    return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "success": "用户状态已更新"})

@router.post("/{user_id}/delete")
async def delete_user(request: Request, user_id: int, current_user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "用户不存在"})
    
    if user.id == current_user["user_id"]:
        return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "error": "不能删除自己"})
    
    target_name = user.username
    db.delete(user)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, current_user["user_id"], "delete_user", f"用户 {target_name}", "删除用户", client_host)
    
    return templates.TemplateResponse("users/list.html", {"request": request, "current_user": current_user, "users": db.query(User).all(), "success": "用户已删除"})