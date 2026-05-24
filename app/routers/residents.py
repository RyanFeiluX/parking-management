from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime

from ..models import Resident, Vehicle, PaymentRecord, OperationLog
from ..deps import require_role, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def log_operation(db: Session, user_id: int, action_type: str, target: str, detail: str, ip_address: str):
    log = OperationLog(
        user_id=user_id,
        action_type=action_type,
        target=target,
        detail=detail,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()

def calculate_payment_status(vehicle, db):
    from ..utils import get_vehicle_payment_status
    return get_vehicle_payment_status(vehicle, db)

@router.get("/")
async def list_residents(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    search_query = request.query_params.get("q", "")
    
    query = db.query(Resident)
    if search_query:
        query = query.filter(
            (Resident.room_number.ilike(f"%{search_query}%")) |
            (Resident.owner_name.ilike(f"%{search_query}%")) |
            (Resident.phone.ilike(f"%{search_query}%"))
        )
    
    residents = query.all()
    
    resident_data = []
    for r in residents:
        vehicle_count = len(r.vehicles)
        expired_count = 0
        for v in r.vehicles:
            status = calculate_payment_status(v, db)
            if status["status"] == "过期":
                expired_count += 1
        resident_data.append({
            "resident": r,
            "vehicle_count": vehicle_count,
            "expired_count": expired_count
        })
    
    return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": resident_data, "search_query": search_query})

@router.get("/add")
async def add_resident_page(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    return templates.TemplateResponse("residents/form.html", {"request": request, "current_user": user})

@router.post("/add")
async def add_resident(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    room_number = form_data.get("room_number")
    owner_name = form_data.get("owner_name")
    phone = form_data.get("phone")
    remark = form_data.get("remark")
    
    db = request.state.db
    
    existing = db.query(Resident).filter_by(room_number=room_number).first()
    if existing:
        return templates.TemplateResponse("residents/form.html", {"request": request, "current_user": user, "error": "房号已存在"})
    
    resident = Resident(
        room_number=room_number,
        owner_name=owner_name,
        phone=phone,
        remark=remark
    )
    db.add(resident)
    db.commit()
    
    log_operation(db, user["user_id"], "create_resident", f"住户 {room_number}", f"创建住户: {owner_name}", request.client.host)
    
    return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "success": "住户创建成功"})

@router.get("/{resident_id}")
async def resident_detail(request: Request, resident_id: int, user: dict = Depends(require_login)):
    db = request.state.db
    resident = db.query(Resident).filter_by(id=resident_id).first()
    
    if not resident:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
    
    vehicles_with_status = []
    for vehicle in resident.vehicles:
        status = calculate_payment_status(vehicle, db)
        latest_payment = vehicle.payments[0] if vehicle.payments else None
        vehicles_with_status.append({
            "vehicle": vehicle,
            "status": status,
            "latest_payment": latest_payment
        })
    
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": vehicles_with_status})

@router.get("/{resident_id}/edit")
async def edit_resident_page(request: Request, resident_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    resident = db.query(Resident).filter_by(id=resident_id).first()
    if not resident:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
    return templates.TemplateResponse("residents/form.html", {"request": request, "current_user": user, "resident": resident})

@router.post("/{resident_id}/edit")
async def edit_resident(request: Request, resident_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    owner_name = form_data.get("owner_name")
    phone = form_data.get("phone")
    remark = form_data.get("remark")
    
    db = request.state.db
    resident = db.query(Resident).filter_by(id=resident_id).first()
    if not resident:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
    
    resident.owner_name = owner_name
    resident.phone = phone
    resident.remark = remark
    db.commit()
    
    log_operation(db, user["user_id"], "update_resident", f"住户 {resident.room_number}", f"修改住户信息", request.client.host)
    
    return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "success": "住户信息已更新"})

@router.post("/{resident_id}/delete")
async def delete_resident(request: Request, resident_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    resident = db.query(Resident).filter_by(id=resident_id).first()
    if not resident:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
    
    target_name = f"住户 {resident.room_number}"
    
    for vehicle in resident.vehicles:
        db.query(PaymentRecord).filter_by(vehicle_id=vehicle.id).delete()
        db.delete(vehicle)
    
    db.delete(resident)
    db.commit()
    
    log_operation(db, user["user_id"], "delete_resident", target_name, "删除住户及关联车辆", request.client.host)
    
    return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "success": "住户已删除"})