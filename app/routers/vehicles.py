from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, date

from ..models import Vehicle, Resident, Invoice, PaymentRecord, OperationLog
from ..deps import require_role, require_login

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

@router.post("/{resident_id}/add")
async def add_vehicle(request: Request, resident_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    plate_number = form_data.get("plate_number")
    brand = form_data.get("brand")
    color = form_data.get("color")
    vehicle_type = form_data.get("vehicle_type", "小车")
    is_garage = form_data.get("is_garage") == "on"
    garage_number = form_data.get("garage_number", "").strip() or None
    garage_valid_until_str = form_data.get("garage_valid_until")
    
    db = request.state.db
    resident = db.query(Resident).filter_by(id=resident_id).first()
    
    if not resident:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
    
    # 检查车辆数量限制（最多8辆）
    current_count = db.query(Vehicle).filter_by(resident_id=resident_id).count()
    if current_count >= 8:
        vehicles_with_status = get_vehicles_with_status(resident, db)
        return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": vehicles_with_status, "error": "最多只能添加8辆车"})
    
    existing = db.query(Vehicle).filter_by(plate_number=plate_number).first()
    if existing:
        vehicles_with_status = get_vehicles_with_status(resident, db)
        return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": vehicles_with_status, "error": "车牌号已存在"})
    
    # 检查车库编号唯一性
    if garage_number:
        existing_garage = db.query(Vehicle).filter(
            Vehicle.garage_number == garage_number,
            Vehicle.id != 0
        ).first()
        if existing_garage:
            vehicles_with_status = get_vehicles_with_status(resident, db)
            return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": vehicles_with_status, "error": f"车库编号 {garage_number} 已被车辆 {existing_garage.plate_number} 使用"})
    
    # 解析车库有效期
    garage_valid_until = None
    if garage_valid_until_str and is_garage:
        try:
            garage_valid_until = datetime.strptime(garage_valid_until_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    max_sort = current_count
    vehicle = Vehicle(
        plate_number=plate_number,
        brand=brand,
        color=color,
        vehicle_type=vehicle_type,
        sort_order=max_sort + 1,
        resident_id=resident_id,
        is_garage=is_garage,
        garage_number=garage_number if is_garage else None,
        garage_valid_until=garage_valid_until if is_garage else None
    )
    db.add(vehicle)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "create_vehicle", f"车辆 {plate_number}", f"为住户 {resident.room_number} 添加车辆{'（车库车）' if is_garage else ''}", client_host)
    
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db), "success": "车辆添加成功"})

def get_vehicles_with_status(resident, db):
    vehicles_with_status = []
    for v in resident.vehicles:
        from ..utils import get_vehicle_payment_status
        status = get_vehicle_payment_status(v, db)
        latest_payment = v.payments[0] if v.payments else None
        vehicles_with_status.append({"vehicle": v, "status": status, "latest_payment": latest_payment})
    return vehicles_with_status

@router.get("/{vehicle_id}/edit")
async def edit_vehicle_page(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    return templates.TemplateResponse("vehicles/form.html", {"request": request, "current_user": user, "vehicle": vehicle})

@router.post("/{vehicle_id}/edit")
async def edit_vehicle(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    brand = form_data.get("brand")
    color = form_data.get("color")
    vehicle_type = form_data.get("vehicle_type")
    status = form_data.get("status")
    is_garage = form_data.get("is_garage") == "on"
    garage_number = form_data.get("garage_number", "").strip() or None
    garage_valid_until_str = form_data.get("garage_valid_until")
    
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    # 检查车库编号唯一性（排除自己）
    if garage_number:
        existing_garage = db.query(Vehicle).filter(
            Vehicle.garage_number == garage_number,
            Vehicle.id != vehicle.id
        ).first()
        if existing_garage:
            resident = vehicle.resident
            return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db), "error": f"车库编号 {garage_number} 已被车辆 {existing_garage.plate_number} 使用"})
    
    # 解析车库有效期
    garage_valid_until = None
    if garage_valid_until_str and is_garage:
        try:
            garage_valid_until = datetime.strptime(garage_valid_until_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    vehicle.brand = brand
    vehicle.color = color
    vehicle.vehicle_type = vehicle_type
    vehicle.status = status
    vehicle.is_garage = is_garage
    vehicle.garage_number = garage_number if is_garage else None
    vehicle.garage_valid_until = garage_valid_until if is_garage else None
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"修改车辆信息{'（车库车）' if is_garage else ''}", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db), "success": "车辆信息已更新"})

@router.post("/{vehicle_id}/delete")
async def delete_vehicle(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    resident = vehicle.resident
    target_name = f"车辆 {vehicle.plate_number}"
    
    db.delete(vehicle)
    
    remaining_vehicles = db.query(Vehicle).filter_by(resident_id=resident.id).order_by(Vehicle.sort_order).all()
    for idx, v in enumerate(remaining_vehicles, 1):
        v.sort_order = idx
    
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "delete_vehicle", target_name, f"从住户 {resident.room_number} 删除车辆", client_host)
    
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db)})

@router.post("/{vehicle_id}/move-up")
async def move_up(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    if vehicle.sort_order == 1:
        resident = vehicle.resident
        return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db)})
    
    prev_vehicle = db.query(Vehicle).filter_by(resident_id=vehicle.resident_id, sort_order=vehicle.sort_order - 1).first()
    if prev_vehicle:
        vehicle.sort_order, prev_vehicle.sort_order = prev_vehicle.sort_order, vehicle.sort_order
        db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"排序上移", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db)})

@router.post("/{vehicle_id}/move-down")
async def move_down(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    max_sort = db.query(Vehicle).filter_by(resident_id=vehicle.resident_id).count()
    if vehicle.sort_order == max_sort:
        resident = vehicle.resident
        return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db)})
    
    next_vehicle = db.query(Vehicle).filter_by(resident_id=vehicle.resident_id, sort_order=vehicle.sort_order + 1).first()
    if next_vehicle:
        vehicle.sort_order, next_vehicle.sort_order = next_vehicle.sort_order, vehicle.sort_order
        db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"排序下移", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html", {"request": request, "current_user": user, "resident": resident, "vehicles": get_vehicles_with_status(resident, db)})

@router.get("/status")
async def vehicle_status(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    filter_type = request.query_params.get("filter", "all")
    
    vehicles = db.query(Vehicle).all()
    
    free_vehicles = []
    temp_vehicles = []
    expired_vehicles = []
    
    from ..utils import get_vehicle_payment_status, get_system_setting
    
    grace_days = int(get_system_setting(db, "grace_period_days", "15"))
    
    for v in vehicles:
        status = get_vehicle_payment_status(v, db)
        
        if filter_type == "registered" and v.resident_id is None:
            continue
        if filter_type == "unregistered" and v.resident_id is not None:
            continue
        
        has_invoice = db.query(Invoice).join(PaymentRecord).filter(PaymentRecord.vehicle_id == v.id).first() is not None
        
        entry = {"vehicle": v, "status": status, "has_invoice": has_invoice}
        if status["status"] == "免费":
            free_vehicles.append(entry)
        elif status["status"] == "临时":
            temp_vehicles.append(entry)
        elif status["status"] == "过期":
            expired_vehicles.append(entry)
    
    return templates.TemplateResponse("vehicles/status.html", {
        "request": request,
        "current_user": user,
        "free_vehicles": free_vehicles,
        "temp_vehicles": temp_vehicles,
        "expired_vehicles": expired_vehicles,
        "filter_type": filter_type
    })