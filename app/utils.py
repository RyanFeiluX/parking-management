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

def generate_room_number(area: str, building: str, unit: str, room: str, db: Session) -> str:
    """
    根据分段信息生成房号
    :param area: 区域（如 "A区"）
    :param building: 楼号（如 "1"）
    :param unit: 单元号（如 "2"，可为空）
    :param room: 房间号（如 "301"）
    :param db: 数据库会话
    :return: 格式化的房号
    """
    # 清理输入
    area = area.strip() if area else ""
    building = building.strip() if building else ""
    unit = unit.strip() if unit else ""
    room = room.strip() if room else ""
    
    # 获取格式规则
    patterns_str = get_system_setting(db, "room_format_patterns", "A区1幢2单元301室,A区1幢301室,1幢2单元301室,1幢301室")
    patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
    
    # 准备变量字典
    has_area = bool(area)
    has_unit = bool(unit)
    
    # 按优先级匹配格式
    for pattern in patterns:
        # 检测模式需要的字段
        need_area = "{area}" in pattern
        need_unit = "{unit}" in pattern
        
        # 检查是否匹配
        if need_area and not has_area:
            continue
        if need_unit and not has_unit:
            continue
        
        # 生成房号
        result = pattern
        if area:
            result = result.replace("{area}", area)
        else:
            result = result.replace("{area}", "")
        if building:
            result = result.replace("{building}", building)
        if unit:
            result = result.replace("{unit}", unit)
        if room:
            result = result.replace("{room}", room)
        
        # 清理多余的栋、单元等字样（当对应的值为空时）
        if not building:
            result = result.replace("{building}", "")
        if not unit:
            result = result.replace("{unit}", "")
        
        # 清理连续的特殊字符
        result = result.replace("栋栋", "栋")
        result = result.replace("单元单元", "单元")
        result = result.replace("室室", "室")
        
        # 清理末尾的栋、单元等
        result = result.rstrip("栋单元室")
        
        return result if result else f"{building}栋{room}室" if building and room else ""
    
    # 默认格式
    if building and room:
        if area and unit:
            return f"{area}{building}栋{unit}单元{room}室"
        elif area:
            return f"{area}{building}栋{room}室"
        elif unit:
            return f"{building}栋{unit}单元{room}室"
        else:
            return f"{building}栋{room}室"
    
    return ""

def get_area_options(db: Session) -> list:
    """
    获取区域选项列表
    :param db: 数据库会话
    :return: 区域选项列表
    """
    options_str = get_system_setting(db, "area_options", "A区,B区,C区,D区")
    return [opt.strip() for opt in options_str.split(",") if opt.strip()]


def calculate_temp_parking_fee(minutes: int, db: Session) -> dict:
    """
    计算临时停车费用
    :param minutes: 停车时长（分钟）
    :param db: 数据库会话
    :return: 费用信息字典
    """
    rules_str = get_system_setting(db, "temp_parking_rules", '')
    try:
        rules = json.loads(rules_str)
    except json.JSONDecodeError:
        rules = {
            "free_minutes": 30,
            "daily_cap": 20.00,
            "tiers": [
                {"from_hours": 0, "to_hours": 1, "fee": 4.0},
                {"from_hours": 1, "to_hours": 2, "fee": 8.0},
                {"from_hours": 2, "to_hours": 12, "fee": 12.0},
                {"from_hours": 12, "to_hours": 24, "fee": 16.0}
            ],
            "overflow": "daily_reset",
            "rate_type": "tier"
        }
    
    free_minutes = rules.get("free_minutes", 30)
    daily_cap = rules.get("daily_cap", 20.0)
    overflow = rules.get("overflow", "daily_reset")
    rate_type = rules.get("rate_type", "tier")
    
    if minutes <= free_minutes:
        return {
            "fee": 0.0,
            "discounted_fee": 0.0,
            "free_minutes": free_minutes,
            "charged_minutes": 0,
            "rate_type": rate_type,
            "detail": f"免费停放（{minutes}分钟 ≤ {free_minutes}分钟）"
        }
    
    charged_minutes = minutes - free_minutes
    hours = charged_minutes / 60.0
    
    if rate_type == "tier":
        tiers = rules.get("tiers", [])
        tiers.sort(key=lambda x: x["from_hours"])
        
        total_fee = 0.0
        tier_details = []
        
        for tier in tiers:
            from_h = tier["from_hours"]
            to_h = tier["to_hours"]
            tier_fee = tier["fee"]
            
            overlap_start = max(hours, from_h)
            overlap_end = min(hours, to_h)
            
            if overlap_end > overlap_start:
                total_fee += tier_fee
                tier_details.append(f"{from_h}-{to_h}小时: {tier_fee}元")
            elif hours > to_h:
                total_fee += tier_fee
                tier_details.append(f"{from_h}-{to_h}小时: {tier_fee}元")
            elif hours <= to_h:
                total_fee += tier_fee
                tier_details.append(f"{from_h}-{to_h}小时: {tier_fee}元")
                break
    else:
        flat_interval = rules.get("flat_interval", 30)
        flat_rate = rules.get("flat_rate", 5.0)
        
        intervals = (charged_minutes + flat_interval - 1) // flat_interval
        total_fee = intervals * flat_rate
        tier_details = [f"{intervals} × {flat_interval}分钟 = {total_fee:.2f}元"]
    
    if daily_cap > 0 and total_fee > daily_cap:
        total_fee = daily_cap
        tier_details.append(f"超过24小时封顶金额，实收{daily_cap}元")
    
    return {
        "fee": round(total_fee, 2),
        "discounted_fee": round(total_fee, 2),
        "free_minutes": free_minutes,
        "charged_minutes": charged_minutes,
        "rate_type": rate_type,
        "detail": "; ".join(tier_details)
    }