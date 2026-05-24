from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from ..models import Vehicle, Resident, PaymentRecord, User
from ..deps import require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def stats_dashboard(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    
    today = date.today()
    current_month = today.replace(day=1)
    
    free_count = 0
    temp_count = 0
    expired_count = 0
    
    from ..utils import get_vehicle_payment_status
    
    vehicles = db.query(Vehicle).all()
    for v in vehicles:
        status = get_vehicle_payment_status(v, db)
        if status["status"] == "免费":
            free_count += 1
        elif status["status"] == "临时":
            temp_count += 1
        elif status["status"] == "过期":
            expired_count += 1
    
    resident_count = db.query(Resident).count()
    vehicle_count = len(vehicles)
    user_count = db.query(User).filter_by(is_active=True).count()
    
    monthly_payment = db.query(PaymentRecord).filter(
        PaymentRecord.paid_at >= current_month
    ).with_entities(PaymentRecord.amount).all()
    monthly_total = sum(p[0] for p in monthly_payment) if monthly_payment else 0
    
    yearly_payment = db.query(PaymentRecord).filter(
        PaymentRecord.paid_at >= today.replace(month=1, day=1)
    ).with_entities(PaymentRecord.amount).all()
    yearly_total = sum(p[0] for p in yearly_payment) if yearly_payment else 0
    
    monthly_data = []
    for i in range(12):
        month_start = (current_month - relativedelta(months=i)).replace(day=1)
        month_end = month_start + relativedelta(months=1)
        payments = db.query(PaymentRecord).filter(
            PaymentRecord.paid_at >= month_start,
            PaymentRecord.paid_at < month_end
        ).with_entities(PaymentRecord.amount).all()
        monthly_data.append({
            "month": month_start.strftime("%Y-%m"),
            "amount": sum(p[0] for p in payments) if payments else 0
        })
    monthly_data.reverse()
    
    method_stats = []
    try:
        stats_query = db.query(
            PaymentRecord.payment_method,
            func.sum(PaymentRecord.amount)
        ).group_by(PaymentRecord.payment_method).all()
        method_stats = [(s[0], float(s[1])) if s[1] else (s[0], 0) for s in stats_query]
    except Exception:
        method_stats = []
    
    tier_stats = []
    try:
        for i in range(1, 4):
            count = db.query(Vehicle).filter(Vehicle.sort_order == i).count()
            tier_stats.append({"tier": i, "count": count})
    except Exception:
        tier_stats = [{"tier": i, "count": 0} for i in range(1, 4)]
    
    return templates.TemplateResponse("stats/dashboard.html", {
        "request": request,
        "current_user": user,
        "resident_count": resident_count or 0,
        "vehicle_count": vehicle_count or 0,
        "user_count": user_count or 0,
        "free_count": free_count or 0,
        "temp_count": temp_count or 0,
        "expired_count": expired_count or 0,
        "monthly_total": monthly_total or 0,
        "yearly_total": yearly_total or 0,
        "monthly_data": monthly_data or [],
        "method_stats": method_stats or [],
        "tier_stats": tier_stats or []
    })