from fastapi import APIRouter, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
import json

from ..models import Vehicle, Resident, SystemSetting, VehiclePause
from ..utils import validate_plate_number

router = APIRouter()

def get_system_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(SystemSetting).filter_by(key=key).first()
    return setting.value if setting else default

def get_vehicle_payment_status(vehicle, db):
    grace_days = int(get_system_setting(db, "grace_period_days", "15"))
    today = date.today()

    pause = db.query(VehiclePause).filter(
        VehiclePause.vehicle_id == vehicle.id,
        VehiclePause.pause_start <= today,
        VehiclePause.pause_end >= today
    ).first()
    if pause:
        return {
            "status": "暂停",
            "status_start": pause.pause_start.isoformat(),
            "status_end": pause.pause_end.isoformat(),
            "detail": f"暂停中（{pause.pause_start}~{pause.pause_end}）"
        }

    if vehicle.resident_id is None:
        return {
            "status": "临时",
            "status_start": None,
            "status_end": None,
            "detail": "未登记访客车辆"
        }
    
    if not vehicle.payments:
        return {
            "status": "临时",
            "status_start": None,
            "status_end": None,
            "detail": "已登记免缴费" if vehicle.is_garage else "已登记未缴费"
        }
    
    latest_payment = vehicle.payments[0]
    
    paid_to = latest_payment.period_end
    
    today = date.today()
    days_past = (today - paid_to).days
    
    if paid_to >= today:
        return {
            "status": "合约",
            "status_start": latest_payment.period_start.isoformat(),
            "status_end": paid_to.isoformat(),
            "detail": f"合约至{paid_to.strftime('%Y-%m-%d')}"
        }
    elif days_past <= grace_days:
        grace_end = paid_to + datetime.timedelta(days=grace_days)
        remaining_days = (grace_end - today).days
        return {
            "status": "临时",
            "status_start": (paid_to + datetime.timedelta(days=1)).isoformat(),
            "status_end": grace_end.isoformat(),
            "detail": f"宽限期内，还剩{remaining_days}天"
        }
    else:
        expired_since = paid_to + datetime.timedelta(days=grace_days + 1)
        expired_days = (today - expired_since).days
        return {
            "status": "过期",
            "status_start": expired_since.isoformat(),
            "status_end": None,
            "detail": f"已过期{expired_days}天"
        }

def format_temp_pricing_for_api(rules: dict) -> dict:
    if not rules:
        rules = {"free_minutes": 0, "daily_cap": 0, "tiers": [], "overflow": "daily_reset"}
    
    parts = []
    free_min = rules.get("free_minutes", 0)
    daily_cap = rules.get("daily_cap", 0)
    if free_min > 0:
        parts.append(f"{free_min}分钟内免费")
    if daily_cap > 0:
        parts.append(f"24小时封顶{daily_cap}元")
    
    return {
        "free_minutes": free_min,
        "daily_cap": daily_cap,
        "tiers": rules.get("tiers", []),
        "overflow": rules.get("overflow", "daily_reset"),
        "description": "，".join(parts) if parts else "按阶梯计费"
    }

@router.get("/vehicle/{plate_number}/status")
async def vehicle_status(request: Request, plate_number: str):
    valid, msg = validate_plate_number(plate_number)
    if not valid:
        return {"error": msg}
    
    db = request.state.db
    
    api_token_setting = get_system_setting(db, "api_token", "")
    if api_token_setting:
        token = request.query_params.get("token", "")
        if token != api_token_setting:
            return {"error": "unauthorized"}, 401
    
    vehicle = db.query(Vehicle).filter_by(plate_number=plate_number).first()
    
    if not vehicle:
        temp_rules = json.loads(get_system_setting(db, "temp_parking_rules", "{}"))
        return {
            "plate_number": plate_number,
            "query_time": datetime.now().isoformat(),
            "is_registered": False,
            "resident_info": None,
            "payment_status": "临时",
            "status_start": None,
            "status_end": None,
            "status_detail": "未登记访客车辆",
            "temp_pricing": format_temp_pricing_for_api(temp_rules),
            "temp_history": None
        }
    
    status_info = get_vehicle_payment_status(vehicle, db)
    temp_rules = json.loads(get_system_setting(db, "temp_parking_rules", "{}"))
    
    resident_info = None
    if vehicle.resident:
        resident_info = {
            "room_number": vehicle.resident.room_number,
            "owner_name": vehicle.resident.owner_name
        }
    
    temp_history = None
    if vehicle.resident_id:
        first_payment = None
        if vehicle.payments:
            first_payment = sorted(vehicle.payments, key=lambda p: p.period_start)[0]
        
        if first_payment:
            paid_from = first_payment.period_start
            
            if vehicle.created_at.date() < paid_from:
                temp_days = (paid_from - vehicle.created_at.date()).days
                daily_cap = temp_rules.get("daily_cap", 0)
                est_fee = temp_days * daily_cap
                temp_history = {
                    "from_date": vehicle.created_at.date().isoformat(),
                    "to_date": (paid_from - datetime.timedelta(days=1)).isoformat(),
                    "temp_days": temp_days,
                    "estimated_daily_charge": daily_cap,
                    "estimated_fee": est_fee,
                    "note": f"按{daily_cap}元/天封顶计算，{temp_days}天共{est_fee}元"
                }
    
    return {
        "plate_number": plate_number,
        "query_time": datetime.now().isoformat(),
        "is_registered": vehicle.resident_id is not None,
        "resident_info": resident_info,
        "payment_status": status_info["status"],
        "status_start": status_info["status_start"],
        "status_end": status_info["status_end"],
        "status_detail": status_info["detail"],
        "temp_pricing": format_temp_pricing_for_api(temp_rules),
        "temp_history": temp_history
    }