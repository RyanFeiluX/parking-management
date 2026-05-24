from datetime import date, datetime, timedelta
from calendar import monthrange
from sqlalchemy.orm import Session
import json

from .models import FeeTier, DiscountPolicy, SystemSetting, PaymentRecord

def get_system_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(SystemSetting).filter_by(key=key).first()
    return setting.value if setting else default

def get_vehicle_payment_status(vehicle, db):
    grace_days = int(get_system_setting(db, "grace_period_days", "15"))
    today = date.today()
    
    # 检查是否是车库车
    if vehicle.is_garage and vehicle.garage_number and vehicle.garage_valid_until:
        if vehicle.garage_valid_until >= today:
            # 车库有效期内：免费
            return {
                "status": "免费",
                "status_start": None,
                "status_end": vehicle.garage_valid_until.isoformat(),
                "detail": f"车库车（{vehicle.garage_number}），有效至{vehicle.garage_valid_until.strftime('%Y-%m-%d')}"
            }
        else:
            # 车库过期：按包月车过期处理（有过期容忍期）
            days_past = (today - vehicle.garage_valid_until).days
            if days_past <= grace_days:
                # 在宽限期内：临时
                grace_end = vehicle.garage_valid_until + timedelta(days=grace_days)
                remaining_days = (grace_end - today).days
                return {
                    "status": "临时",
                    "status_start": (vehicle.garage_valid_until + timedelta(days=1)).isoformat(),
                    "status_end": grace_end.isoformat(),
                    "detail": f"车库已过期，宽限期内(还剩{remaining_days}天)"
                }
            else:
                # 超过宽限期：过期
                expired_since = vehicle.garage_valid_until + timedelta(days=grace_days + 1)
                expired_days = (today - expired_since).days
                return {
                    "status": "过期",
                    "status_start": expired_since.isoformat(),
                    "status_end": None,
                    "detail": f"车库已过期{expired_days}天，请办理延期"
                }
    
    # 非车库车：原有的包月车逻辑
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
            "detail": "已登记未缴费"
        }
    
    latest_payment = vehicle.payments[0]
    
    period_end_str = latest_payment.period_end
    year, month = map(int, period_end_str.split("-"))
    _, last_day = monthrange(year, month)
    paid_to = date(year, month, last_day)
    
    days_past = (today - paid_to).days
    
    if paid_to >= today:
        return {
            "status": "免费",
            "status_start": f"{latest_payment.period_start}-01",
            "status_end": paid_to.isoformat(),
            "detail": f"免费至{paid_to.strftime('%Y-%m-%d')}"
        }
    elif days_past <= grace_days:
        grace_end = paid_to + timedelta(days=grace_days)
        remaining_days = (grace_end - today).days
        return {
            "status": "临时",
            "status_start": (paid_to + timedelta(days=1)).isoformat(),
            "status_end": grace_end.isoformat(),
            "detail": f"到期，宽限期内(还剩{remaining_days}天)"
        }
    else:
        expired_since = paid_to + timedelta(days=grace_days + 1)
        expired_days = (today - expired_since).days
        return {
            "status": "过期",
            "status_start": expired_since.isoformat(),
            "status_end": None,
            "detail": f"已过期{expired_days}天"
        }

def get_applicable_fee_tier(vehicle, db):
    sort_order = vehicle.sort_order
    
    today = date.today()
    period_start_date = today
    
    tier = db.query(FeeTier).filter(
        FeeTier.seq_from <= sort_order,
        FeeTier.seq_to >= sort_order,
        FeeTier.effective_date <= period_start_date,
        (FeeTier.expired_at.is_(None) | (FeeTier.expired_at > datetime.now()))
    ).order_by(FeeTier.effective_date.desc()).first()
    
    return tier

def get_applicable_discount(vehicle, db):
    if not vehicle.resident:
        return None
    
    sort_order = vehicle.sort_order
    vehicle_type = vehicle.vehicle_type
    room_number = vehicle.resident.room_number
    
    today = date.today()
    
    discounts = db.query(DiscountPolicy).filter(
        DiscountPolicy.apply_seq_from <= sort_order,
        DiscountPolicy.apply_seq_to >= sort_order,
        DiscountPolicy.effective_date <= today,
        (DiscountPolicy.expired_at.is_(None) | (DiscountPolicy.expired_at > datetime.now()))
    ).order_by(DiscountPolicy.effective_date.desc()).all()
    
    for discount in discounts:
        if discount.scope_type == "all":
            return discount
        elif discount.scope_type == "vehicle_type" and vehicle_type == discount.scope_value:
            return discount
        elif discount.scope_type == "room_prefix" and room_number.startswith(discount.scope_value):
            return discount
    
    return None

def calculate_payment_amount(vehicle, period_type, months, db):
    if vehicle.is_garage:
        return {"amount": 0, "base_amount": 0, "discount_amount": 0, "summary": "车库车 - 无需缴费", "tier": None, "discount": None}
    
    tier = get_applicable_fee_tier(vehicle, db)
    discount = get_applicable_discount(vehicle, db)
    
    if not tier:
        return {"amount": 0, "base_amount": 0, "discount_amount": 0, "summary": "未找到适用档位", "tier": None, "discount": None}
    
    period_months = months
    if period_type == "季":
        period_months = months * 3
    elif period_type == "年":
        period_months = months * 12
    
    monthly_fee = float(tier.monthly_fee)
    
    if period_type == "月":
        base_amount = monthly_fee * months
    elif period_type == "季":
        if tier.quarterly_fee:
            base_amount = float(tier.quarterly_fee) * months
        else:
            base_amount = monthly_fee * 3 * months
    elif period_type == "年":
        if tier.yearly_fee:
            base_amount = float(tier.yearly_fee) * months
        else:
            base_amount = monthly_fee * 12 * months
    else:
        base_amount = monthly_fee * months
    
    discount_amount = 0
    final_amount = base_amount
    discount_info = ""
    
    if discount:
        if discount.discount_type == "free":
            final_amount = 0
            discount_amount = base_amount
            discount_info = f"{discount.name}(免费)"
        elif discount.discount_type == "discount_percent":
            discount_amount = base_amount * (1 - float(discount.discount_value))
            final_amount = base_amount * float(discount.discount_value)
            discount_info = f"{discount.name}({int(float(discount.discount_value)*100)}折)"
        elif discount.discount_type == "fixed_fee":
            discount_amount = base_amount - float(discount.discount_value)
            final_amount = float(discount.discount_value)
            discount_info = f"{discount.name}(固定{float(discount.discount_value)}元)"
    
    summary_parts = [f"第{vehicle.sort_order}辆车 {monthly_fee}元/月 × {period_months}个月 = {base_amount:.2f}元"]
    if discount_info:
        summary_parts.append(f"{discount_info} → 实付{final_amount:.2f}元")
    
    return {
        "amount": round(final_amount, 2),
        "base_amount": round(base_amount, 2),
        "discount_amount": round(discount_amount, 2),
        "summary": "，".join(summary_parts),
        "tier": tier,
        "discount": discount
    }