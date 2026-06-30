from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import OperationLog, User
from ..deps import require_role

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def list_logs(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    
    start_date = request.query_params.get("start_date", "")
    end_date = request.query_params.get("end_date", "")
    action_type = request.query_params.get("action_type", "")
    username = request.query_params.get("username", "")
    
    query = db.query(OperationLog).order_by(OperationLog.created_at.desc())
    
    if start_date:
        query = query.filter(OperationLog.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(OperationLog.created_at <= datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1))
    if action_type:
        query = query.filter(OperationLog.action_type == action_type)
    if username:
        user_obj = db.query(User).filter_by(username=username).first()
        if user_obj:
            query = query.filter(OperationLog.user_id == user_obj.id)
    
    logs = query.all()
    
    log_data = []
    for log in logs:
        user_obj = db.query(User).filter_by(id=log.user_id).first() if log.user_id else None
        log_data.append({
            "log": log,
            "user": user_obj
        })
    
    action_types = ["login", "logout", "create_user", "update_user", "delete_user",
                   "create_resident", "update_resident", "delete_resident",
                   "create_vehicle", "update_vehicle", "delete_vehicle",
                   "payment", "update_fee_tier", "create_discount", "update_discount",
                   "create_invoice", "update_invoice", "complete_invoice", "cancel_invoice",
                   "export_data", "system_backup"]
    
    return templates.TemplateResponse("logs/list.html", {
        "request": request,
        "current_user": user,
        "logs": log_data,
        "start_date": start_date,
        "end_date": end_date,
        "action_type": action_type,
        "username": username,
        "action_types": action_types
    })