from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from ..models import PaymentRecord, Vehicle, Resident, User, OperationLog
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
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "amount_info": amount_info,
        "plate_number": plate_number
    })

@router.post("/calculate")
async def calculate_amount(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    plate_number = form_data.get("plate_number")
    period_type = form_data.get("period_type", "月")
    months = int(form_data.get("months", 1))
    
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(plate_number=plate_number).first()
    
    if not vehicle:
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "current_user": user,
            "error": "车辆不存在",
            "plate_number": plate_number,
            "period_type": period_type,
            "months": months
        })
    
    from ..utils import calculate_payment_amount
    amount_info = calculate_payment_amount(vehicle, period_type, months, db)
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "amount_info": amount_info,
        "plate_number": plate_number,
        "period_type": period_type,
        "months": months
    })

@router.post("/pay")
async def pay(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    vehicle_id = int(form_data.get("vehicle_id"))
    period_type = form_data.get("period_type")
    months = int(form_data.get("months"))
    amount = float(form_data.get("amount"))
    payment_method = form_data.get("payment_method")
    remark = form_data.get("remark")
    
    db = request.state.db
    vehicle = db.query(Vehicle).filter_by(id=vehicle_id).first()
    
    if not vehicle:
        return templates.TemplateResponse("payments/form.html", {
            "request": request,
            "current_user": user,
            "error": "车辆不存在"
        })
    
    today = date.today()
    period_start = today.strftime("%Y-%m")
    
    if period_type == "月":
        end_date = today + relativedelta(months=months)
    elif period_type == "季":
        end_date = today + relativedelta(months=months * 3)
    elif period_type == "年":
        end_date = today + relativedelta(months=months * 12)
    else:
        end_date = today + relativedelta(months=months)
    
    period_end = end_date.strftime("%Y-%m")
    
    from ..utils import calculate_payment_amount
    amount_info = calculate_payment_amount(vehicle, period_type, months, db)
    
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
    db.commit()
    
    log_operation(db, user["user_id"], "payment", f"车辆 {vehicle.plate_number}", f"缴费 {amount}元，{period_type}{months}期", request.client.host)
    
    return templates.TemplateResponse("payments/form.html", {
        "request": request,
        "current_user": user,
        "vehicle": vehicle,
        "success": f"缴费成功！已缴纳 {amount} 元，{period_type}{months}期",
        "plate_number": vehicle.plate_number
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
        payment_data.append({
            "payment": p,
            "vehicle": vehicle,
            "resident": resident,
            "operator": operator
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