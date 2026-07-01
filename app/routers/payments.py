from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from calendar import monthrange

from ..models import PaymentRecord, Vehicle, Resident, User, OperationLog, VehiclePause
from dateutil.relativedelta import relativedelta
from ..deps import require_role, require_login
from ..jinja import templates

router = APIRouter()

def calc_period_end(period_start: date, period_type: str, months: int) -> date:
    if period_type == "季":
        months *= 3
    elif period_type == "年":
        months *= 12
    return period_start + relativedelta(months=months) - relativedelta(days=1)

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
async def payment_form(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    plate_number = request.query_params.get("plate", "")
    
    vehicle = None
    amount_info = None
    
    if plate_number:
        vehicle = db.query(Vehicle).filter_by(plate_number=plate_number).first()
        if vehicle:
            from ..utils import calculate_payment_amount
            amount_info = calculate_payment_amount(vehicle, "月", 1, db)
    
    today = date.today()
    pause_records = []
    if vehicle:
        pause_records = db.query(VehiclePause).filter_by(vehicle_id=vehicle.id).order_by(VehiclePause.pause_start).all()
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "amount_info": amount_info,
        "plate_number": plate_number,
        "period_start": today,
        "pause_records": pause_records
    })

@router.post("/calculate")
async def calculate_amount(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    plate_number = form_data.get("plate_number")
    period_type = form_data.get("period_type", "月")
    months = int(form_data.get("months", 1))
    period_start_str = form_data.get("period_start", "")
    pause_start_str = form_data.get("pause_start", "")
    pause_months = int(form_data.get("pause_months", 0))
    
    try:
        period_start = datetime.strptime(period_start_str, "%Y-%m-%d").date() if period_start_str else date.today()
    except ValueError:
        period_start = date.today()
    
    period_end = calc_period_end(period_start, period_type, months)
    
    # 验证暂停字段
    pause_start = None
    pause_end = None
    if pause_months > 0:
        try:
            pause_start = datetime.strptime(pause_start_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return JSONResponse({"error": "设置了暂停月数但未填写暂停起始日期"})
        if pause_start < date.today():
            return JSONResponse({"error": "暂停起始日期不能早于今天"})
        if pause_start < period_start or pause_start > period_end:
            return JSONResponse({"error": "暂停起始日期必须在缴费周期范围内"})
        pause_end = pause_start + relativedelta(months=pause_months) - relativedelta(days=1)
        if pause_end > period_end:
            return JSONResponse({"error": "暂停区间超出缴费周期范围"})
    
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(plate_number=plate_number).first()
    
    if not vehicle:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"error": "车辆不存在"})
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "current_user": user,
            "error": "车辆不存在",
            "plate_number": plate_number,
            "period_type": period_type,
            "months": months,
            "period_start": period_start
        })
    
    from ..utils import calculate_payment_amount, check_period_overlap
    amount_info = calculate_payment_amount(vehicle, period_type, months, db, pause_months)
    warnings = check_period_overlap(vehicle.id, period_start, period_end, db)
    
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        resp = {
            "summary": amount_info.get("summary", ""),
            "amount": amount_info.get("amount", 0),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "warnings": warnings
        }
        if pause_start:
            resp["pause_start"] = pause_start.isoformat()
            resp["pause_end"] = pause_end.isoformat()
            resp["pause_months"] = pause_months
        return JSONResponse(resp)
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "amount_info": amount_info,
        "plate_number": plate_number,
        "period_type": period_type,
        "months": months,
        "period_start": period_start
    })

@router.post("/pay")
async def pay(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    vehicle_id = int(form_data.get("vehicle_id"))
    period_type = form_data.get("period_type")
    months = int(form_data.get("months"))
    period_start_str = form_data.get("period_start", "")
    payment_method = form_data.get("payment_method")
    remark = form_data.get("remark")
    pause_start_str = form_data.get("pause_start", "")
    pause_months = int(form_data.get("pause_months", 0))
    
    try:
        period_start = datetime.strptime(period_start_str, "%Y-%m-%d").date() if period_start_str else date.today()
    except ValueError:
        period_start = date.today()
    
    period_end = calc_period_end(period_start, period_type, months)
    
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    
    if not vehicle:
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "current_user": user,
            "error": "车辆不存在"
        })
    
    pause_records = db.query(VehiclePause).filter_by(vehicle_id=vehicle.id).order_by(VehiclePause.pause_start).all()
    
    # 验证暂停字段
    pause_start = None
    pause_end = None
    if pause_months > 0:
        try:
            pause_start = datetime.strptime(pause_start_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return templates.TemplateResponse("payments/form.html", {
                "request": request, "current_user": user, "vehicle": vehicle,
                "error": "设置了暂停月数但未填写暂停起始日期",
                "pause_records": pause_records
            })
        if pause_start < date.today():
            return templates.TemplateResponse("payments/form.html", {
                "request": request, "current_user": user, "vehicle": vehicle,
                "error": "暂停起始日期不能早于今天",
                "pause_records": pause_records
            })
        if pause_start < period_start or pause_start > period_end:
            return templates.TemplateResponse("payments/form.html", {
                "request": request, "current_user": user, "vehicle": vehicle,
                "error": "暂停起始日期必须在缴费周期范围内",
                "pause_records": pause_records
            })
        pause_end = pause_start + relativedelta(months=pause_months) - relativedelta(days=1)
        if pause_end > period_end:
            return templates.TemplateResponse("payments/form.html", {
                "request": request, "current_user": user, "vehicle": vehicle,
                "error": "暂停区间超出缴费周期范围",
                "pause_records": pause_records
            })
    
    from ..utils import calculate_payment_amount
    amount_info = calculate_payment_amount(vehicle, period_type, months, db, pause_months)
    amount = amount_info["amount"]
    
    if amount <= 0:
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "current_user": user,
            "vehicle": vehicle,
            "error": "缴费金额必须大于0",
            "pause_records": pause_records
        })
    
    payment = PaymentRecord(
        vehicle_id=vehicle_id,
        period_start=period_start,
        period_end=period_end,
        period_type=period_type,
        amount=amount,
        rule_summary=amount_info.get("summary", ""),
        payment_method=payment_method,
        operator_id=user["user_id"],
        remark=remark
    )
    
    db.add(payment)
    db.flush()
    
    # 创建暂停记录
    new_pause_id = None
    if pause_start and pause_months > 0:
        vp = VehiclePause(
            vehicle_id=vehicle_id,
            payment_id=payment.id,
            pause_start=pause_start,
            pause_end=pause_end,
            pause_months=pause_months
        )
        db.add(vp)
        db.flush()
        new_pause_id = vp.id
    
    # 删除被新缴费覆盖的暂停记录（排除新建的）
    covered_pauses = db.query(VehiclePause).filter(
        VehiclePause.vehicle_id == vehicle_id,
        VehiclePause.pause_start >= period_start,
        VehiclePause.pause_end <= period_end,
    ).all()
    for cvp in covered_pauses:
        if cvp.id == new_pause_id:
            continue
        db.delete(cvp)
    
    db.commit()
    
    detail_parts = [f"缴费 {amount}元，{period_type}{months}期，{period_start}~{period_end}"]
    if pause_start:
        detail_parts.append(f"暂停{pause_months}个月({pause_start}~{pause_end})")
    if covered_pauses:
        detail_parts.append(f"覆盖了{len(covered_pauses)}条暂停记录")
    detail = "，".join(detail_parts)
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "payment", f"车辆 {vehicle.plate_number}", detail, client_host)
    
    pause_records = db.query(VehiclePause).filter_by(vehicle_id=vehicle.id).order_by(VehiclePause.pause_start).all()
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "success": f"缴费成功！已缴纳 {amount} 元，{period_type}{months}期（{period_start}~{period_end}）",
        "plate_number": vehicle.plate_number,
        "pause_records": pause_records
    })

@router.get("/logs")
async def payment_logs(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    
    start_date = request.query_params.get("start_date", "")
    end_date = request.query_params.get("end_date", "")
    plate_number = request.query_params.get("plate_number", "")
    room_number = request.query_params.get("room_number", "")
    payment_method = request.query_params.get("payment_method", "")
    
    query = db.query(PaymentRecord).order_by(PaymentRecord.paid_at.desc())
    
    if start_date:
        query = query.filter(PaymentRecord.paid_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(PaymentRecord.paid_at <= datetime.strptime(end_date, "%Y-%m-%d") + relativedelta(days=1))
    if plate_number:
        query = query.join(Vehicle).filter(Vehicle.plate_number.ilike(f"%{plate_number}%"))
    if room_number:
        query = query.join(Vehicle).join(Resident).filter(Resident.room_number.ilike(f"%{room_number}%"))
    if payment_method:
        query = query.filter(PaymentRecord.payment_method == payment_method)
    
    payments = query.all()
    
    payment_data = []
    for p in payments:
        vehicle = p.vehicle
        resident = vehicle.resident if vehicle else None
        operator = db.query(User).filter_by(id=p.operator_id).first() if p.operator_id else None
        pauses = db.query(VehiclePause).filter_by(payment_id=p.id).order_by(VehiclePause.pause_start).all()
        payment_data.append({
            "payment": p,
            "vehicle": vehicle,
            "resident": resident,
            "operator": operator,
            "pauses": pauses
        })
    
    return templates.TemplateResponse("payments/logs.html", {
        "request": request,
        "current_user": user,
        "payments": payment_data,
        "start_date": start_date,
        "end_date": end_date,
        "plate_number": plate_number,
        "room_number": room_number,
        "payment_method": payment_method
    })

@router.get("/arrears")
async def arrears_list(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    
    from ..utils import get_vehicle_payment_status
    
    vehicles = db.query(Vehicle).all()
    arrears = []
    
    for v in vehicles:
        status = get_vehicle_payment_status(v, db)
        if status["status"] == "过期":
            latest_payment = v.payments[0] if v.payments else None
            arrears.append({"vehicle": v, "status": status, "latest_payment": latest_payment})
    
    return templates.TemplateResponse("payments/arrears.html", {
        "request": request,
        "current_user": user,
        "arrears": arrears
    })