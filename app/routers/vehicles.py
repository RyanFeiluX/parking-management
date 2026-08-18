from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date

from ..models import Vehicle, Resident, VehiclePause, Invoice, PaymentRecord, OperationLog
from ..deps import require_role, require_login
from ..utils import validate_plate_number
from ..jinja import templates
from .residents import build_resident_detail_context

router = APIRouter()

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
    
    valid, msg = validate_plate_number(plate_number)
    if not valid:
        db = request.state.db
        resident = db.query(Resident).filter_by(id=resident_id).first()
        if not resident:
            return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "住户不存在"})
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user, extra={"error": msg}))
    
    brand = form_data.get("brand")
    color = form_data.get("color")
    vehicle_type = form_data.get("vehicle_type", "小车")
    remark = form_data.get("remark", "").strip() or None
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
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user, extra={"error": "最多只能添加8辆车"}))
    
    existing = db.query(Vehicle).filter_by(plate_number=plate_number).first()
    if existing:
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user, extra={"error": "车牌号已存在"}))
    
    # 检查车库编号唯一性
    if garage_number:
        existing_garage = db.query(Vehicle).filter(
            Vehicle.garage_number == garage_number,
            Vehicle.id != 0
        ).first()
        if existing_garage:
            return templates.TemplateResponse("residents/detail.html",
                build_resident_detail_context(resident, db, request, user,
                    extra={"error": f"车库编号 {garage_number} 已被车辆 {existing_garage.plate_number} 使用"}))
    
    # 解析车库有效期
    garage_valid_until = None
    if garage_valid_until_str and is_garage:
        try:
            garage_valid_until = datetime.strptime(garage_valid_until_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Resolve vehicle sort order
    sort_order_input = form_data.get("sort_order")

    # Calculate current max sort order for the resident
    max_sort_row = db.query(func.max(Vehicle.sort_order)).filter_by(resident_id=resident_id).first()
    max_sort_order = max_sort_row[0] if max_sort_row[0] is not None else 0

    if sort_order_input:
        try:
            sort_order = int(sort_order_input)
        except ValueError:
            sort_order = max_sort_order + 1
    else:
        sort_order = max_sort_order + 1

    # Clamp to valid 1..8 range (business rule: max 8 vehicles per resident)
    sort_order = max(1, min(sort_order, 8))

    # If the requested sort_order is already taken, shift later vehicles backward
    existing_with_sort = db.query(Vehicle).filter_by(
        resident_id=resident_id, sort_order=sort_order
    ).first()
    if existing_with_sort:
        vehicles_to_shift = db.query(Vehicle).filter(
            Vehicle.resident_id == resident_id,
            Vehicle.sort_order >= sort_order
        ).order_by(Vehicle.sort_order.desc()).all()
        for v in vehicles_to_shift:
            v.sort_order += 1
    
    vehicle = Vehicle(
        plate_number=plate_number,
        brand=brand,
        color=color,
        vehicle_type=vehicle_type,
        sort_order=sort_order,
        resident_id=resident_id,
        is_garage=is_garage,
        garage_number=garage_number if is_garage else None,
        garage_valid_until=garage_valid_until if is_garage else None,
        remark=remark
    )
    db.add(vehicle)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "create_vehicle", f"车辆 {plate_number}", f"为住户 {resident.room_number} 添加车辆{'（车库车）' if is_garage else ''}", client_host)
    
    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user, extra={"success": "车辆添加成功"}))

@router.get("/{vehicle_id}/edit")
async def edit_vehicle_page(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    return templates.TemplateResponse("vehicles/form.html", {"request": request, "current_user": user, "vehicle": vehicle})

@router.get("/{vehicle_id}/sort-order-preview")
async def sort_order_preview(request: Request, vehicle_id: int, new_sort: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return {"error": "车辆不存在"}
    
    current_sort_order = vehicle.sort_order
    resident_id = vehicle.resident_id
    
    # Clamp to business rule: sort_order must be in 1..8
    new_sort_order = max(1, min(new_sort, 8))
    
    if new_sort_order == current_sort_order:
        return {"affected": []}
    
    affected = []
    if new_sort_order < current_sort_order:
        vehicles_to_shift = db.query(Vehicle).filter(
            Vehicle.resident_id == resident_id,
            Vehicle.sort_order >= new_sort_order,
            Vehicle.sort_order < current_sort_order,
            Vehicle.id != vehicle.id
        ).order_by(Vehicle.sort_order.desc()).all()
        for v in vehicles_to_shift:
            affected.append({
                "plate_number": v.plate_number,
                "current_sort": v.sort_order,
                "new_sort": v.sort_order + 1,
                "change": "+1"
            })
    else:
        vehicles_to_shift = db.query(Vehicle).filter(
            Vehicle.resident_id == resident_id,
            Vehicle.sort_order > current_sort_order,
            Vehicle.sort_order <= new_sort_order,
            Vehicle.id != vehicle.id
        ).order_by(Vehicle.sort_order.asc()).all()
        for v in vehicles_to_shift:
            affected.append({
                "plate_number": v.plate_number,
                "current_sort": v.sort_order,
                "new_sort": v.sort_order - 1,
                "change": "-1"
            })
    
    return {"affected": affected}

@router.post("/{vehicle_id}/edit")
async def edit_vehicle(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    brand = form_data.get("brand")
    color = form_data.get("color")
    vehicle_type = form_data.get("vehicle_type")
    status = form_data.get("status")
    remark = form_data.get("remark", "").strip() or None
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
            return templates.TemplateResponse("residents/detail.html",
                build_resident_detail_context(resident, db, request, user,
                    extra={"error": f"车库编号 {garage_number} 已被车辆 {existing_garage.plate_number} 使用"}))
    
    # 解析车库有效期
    garage_valid_until = None
    if garage_valid_until_str and is_garage:
        try:
            garage_valid_until = datetime.strptime(garage_valid_until_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # 处理车辆序号
    sort_order_input = form_data.get("sort_order")
    if sort_order_input:
        try:
            new_sort_order = int(sort_order_input)
        except ValueError:
            new_sort_order = vehicle.sort_order
    else:
        new_sort_order = vehicle.sort_order
    
    current_sort_order = vehicle.sort_order
    resident_id = vehicle.resident_id
    
    # Clamp sort order to business rule 1..8
    new_sort_order = max(1, min(new_sort_order, 8))
    
    # Adjust sort orders of sibling vehicles if the order changed
    if new_sort_order != current_sort_order:
        if new_sort_order < current_sort_order:
            # Moving earlier: shift vehicles in [new, current) forward by +1
            vehicles_to_shift = db.query(Vehicle).filter(
                Vehicle.resident_id == resident_id,
                Vehicle.sort_order >= new_sort_order,
                Vehicle.sort_order < current_sort_order,
                Vehicle.id != vehicle.id
            ).order_by(Vehicle.sort_order.desc()).all()
            for v in vehicles_to_shift:
                v.sort_order += 1
        else:
            # Moving later: shift vehicles in (current, new] backward by -1
            vehicles_to_shift = db.query(Vehicle).filter(
                Vehicle.resident_id == resident_id,
                Vehicle.sort_order > current_sort_order,
                Vehicle.sort_order <= new_sort_order,
                Vehicle.id != vehicle.id
            ).order_by(Vehicle.sort_order.asc()).all()
            for v in vehicles_to_shift:
                v.sort_order -= 1
    
    vehicle.sort_order = new_sort_order
    vehicle.brand = brand
    vehicle.color = color
    vehicle.vehicle_type = vehicle_type
    vehicle.status = status
    vehicle.remark = remark
    vehicle.is_garage = is_garage
    vehicle.garage_number = garage_number if is_garage else None
    vehicle.garage_valid_until = garage_valid_until if is_garage else None
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"修改车辆信息{'（车库车）' if is_garage else ''}", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user, extra={"success": "车辆信息已更新"}))

@router.post("/{vehicle_id}/delete")
async def delete_vehicle(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    resident = vehicle.resident
    target_name = f"车辆 {vehicle.plate_number}"
    
    db.query(VehiclePause).filter_by(vehicle_id=vehicle_id).delete()
    db.query(PaymentRecord).filter_by(vehicle_id=vehicle_id).delete()
    db.delete(vehicle)
    
    # Intentionally NOT re-indexing remaining vehicle sort_order numbers,
    # because sort_order represents a stable business vehicle number (e.g. the
    # 5th car of the household), not a 1..N display sequential index. Display
    # ordering is handled by loop.index in the template.
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "delete_vehicle", target_name, f"从住户 {resident.room_number} 删除车辆", client_host)
    
    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user))

@router.post("/{vehicle_id}/move-up")
async def move_up(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    if vehicle.sort_order == 1:
        resident = vehicle.resident
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user))
    
    # Find the previous vehicle by sort order (not necessarily -1, since orders can be non-contiguous)
    prev_vehicle = db.query(Vehicle).filter(
        Vehicle.resident_id == vehicle.resident_id,
        Vehicle.sort_order < vehicle.sort_order
    ).order_by(Vehicle.sort_order.desc()).first()
    if prev_vehicle:
        vehicle.sort_order, prev_vehicle.sort_order = prev_vehicle.sort_order, vehicle.sort_order
        db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"排序上移", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user))

@router.post("/{vehicle_id}/move-down")
async def move_down(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not vehicle:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在"})
    
    max_sort_row = db.query(func.max(Vehicle.sort_order)).filter_by(resident_id=vehicle.resident_id).first()
    max_sort = max_sort_row[0] if max_sort_row[0] is not None else 0
    if vehicle.sort_order >= max_sort:
        resident = vehicle.resident
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user))
    
    # Find the next vehicle by sort order (not necessarily +1, since orders can be non-contiguous)
    next_vehicle = db.query(Vehicle).filter(
        Vehicle.resident_id == vehicle.resident_id,
        Vehicle.sort_order > vehicle.sort_order
    ).order_by(Vehicle.sort_order.asc()).first()
    if next_vehicle:
        vehicle.sort_order, next_vehicle.sort_order = next_vehicle.sort_order, vehicle.sort_order
        db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_vehicle", f"车辆 {vehicle.plate_number}", f"排序下移", client_host)
    
    resident = vehicle.resident
    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user))

@router.post("/{vehicle_id}/replace")
async def replace_vehicle(request: Request, vehicle_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    """替换车辆：新建一辆车占用原车辆编号位置，原车变为未登记访客车辆"""
    db = request.state.db
    old_vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    if not old_vehicle or old_vehicle.resident_id is None:
        return templates.TemplateResponse("residents/list.html", {"request": request, "current_user": user, "residents": db.query(Resident).all(), "error": "车辆不存在或已不在住户名下"})

    resident = old_vehicle.resident
    form_data = await request.form()
    new_plate = form_data.get("plate_number")
    valid, msg = validate_plate_number(new_plate)
    if not valid:
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user, extra={"error": msg}))

    # 新车牌若存在于数据库：
    # - 当前归属某住户（生效车辆）→ 拒绝
    # - 未登记访客车（resident_id 为空，含被替换出的历史车）→ 允许，下面接管
    existing = db.query(Vehicle).filter_by(plate_number=new_plate).first()
    if existing and existing.resident_id is not None:
        return templates.TemplateResponse("residents/detail.html",
            build_resident_detail_context(resident, db, request, user,
                extra={"error": "车牌号已存在（当前为生效车辆）"}))

    brand = form_data.get("brand")
    color = form_data.get("color")
    vehicle_type = form_data.get("vehicle_type", "小车")
    remark = (form_data.get("remark") or "").strip() or None

    if existing:
        # 接管未登记访客记录：保留缴费历史，绑定到新住户并标记替换入时间
        new_vehicle = existing
        new_vehicle.resident_id = resident.id
        new_vehicle.sort_order = old_vehicle.sort_order  # 继承车辆编号
        new_vehicle.replaced_in_at = datetime.now()  # 本次替换入时间
        new_vehicle.replaced_out_at = None  # 恢复生效，清除历史替换出标记
        new_vehicle.replacement_vehicle_id = None  # 不再是"被替换出的旧车"
        if brand:
            new_vehicle.brand = brand  # 表单优先，未填保留原值
        if color:
            new_vehicle.color = color
        new_vehicle.vehicle_type = vehicle_type
        if remark:
            new_vehicle.remark = remark
        # 车库属性随编号位置转移给新车
        new_vehicle.is_garage = old_vehicle.is_garage
        new_vehicle.garage_number = old_vehicle.garage_number
        new_vehicle.garage_valid_until = old_vehicle.garage_valid_until
    else:
        # 数据库中不存在该车牌：正常新建
        new_vehicle = Vehicle(
            plate_number=new_plate,
            brand=brand,
            color=color,
            vehicle_type=vehicle_type,
            sort_order=old_vehicle.sort_order,  # 继承车辆编号
            resident_id=old_vehicle.resident_id,
            is_garage=old_vehicle.is_garage,  # 车库随编号位置转移
            garage_number=old_vehicle.garage_number,
            garage_valid_until=old_vehicle.garage_valid_until,
            remark=remark,
            replaced_in_at=datetime.now(),  # 替换入时间
        )
        db.add(new_vehicle)

    db.flush()  # 获得新车辆 id（接管时即访客记录 id）

    # 旧车：变为未登记访客车辆，记录替换出时间与新车关联，清空车库属性
    old_vehicle.resident_id = None
    old_vehicle.replaced_out_at = datetime.now()
    old_vehicle.replacement_vehicle_id = new_vehicle.id
    old_vehicle.is_garage = False
    old_vehicle.garage_number = None
    old_vehicle.garage_valid_until = None

    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "replace_vehicle",
                  f"车辆 {old_vehicle.plate_number} → {new_vehicle.plate_number}",
                  f"住户 {resident.room_number} 车辆编号{old_vehicle.sort_order} 完成替换", client_host)

    return templates.TemplateResponse("residents/detail.html",
        build_resident_detail_context(resident, db, request, user, extra={"success": "车辆替换成功"}))

@router.get("/status")
async def vehicle_status(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    filter_type = request.query_params.get("filter", "all")
    
    vehicles = db.query(Vehicle).all()
    
    free_vehicles = []
    paused_vehicles = []
    contract_vehicles = []
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
        elif status["status"] == "暂停":
            paused_vehicles.append(entry)
        elif status["status"] == "合约":
            contract_vehicles.append(entry)
        elif status["status"] == "临时":
            temp_vehicles.append(entry)
        elif status["status"] == "过期":
            expired_vehicles.append(entry)
    
    return templates.TemplateResponse("vehicles/status.html", {
        "request": request,
        "current_user": user,
        "free_vehicles": free_vehicles,
        "paused_vehicles": paused_vehicles,
        "contract_vehicles": contract_vehicles,
        "temp_vehicles": temp_vehicles,
        "expired_vehicles": expired_vehicles,
        "filter_type": filter_type
    })