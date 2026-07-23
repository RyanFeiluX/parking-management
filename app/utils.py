from datetime import date, datetime, timedelta
from calendar import monthrange
from sqlalchemy.orm import Session
from sqlalchemy import exists
import json

from .models import FeeTier, DiscountPolicy, SystemSetting, PaymentRecord, VehiclePause

def get_system_setting(db: Session, key: str, default: str = "") -> str:
    setting = db.query(SystemSetting).filter_by(key=key).first()
    return setting.value if setting else default

def get_vehicle_payment_status(vehicle, db):
    grace_days = int(get_system_setting(db, "grace_period_days", "15"))
    today = date.today()

    # 检查今天是否在暂停区间内（排除已被后续缴费填补的暂停）
    pause = db.query(VehiclePause).filter(
        VehiclePause.vehicle_id == vehicle.id,
        VehiclePause.pause_start <= today,
        VehiclePause.pause_end >= today,
        ~exists().where(
            PaymentRecord.vehicle_id == VehiclePause.vehicle_id,
            PaymentRecord.id != VehiclePause.payment_id,
            PaymentRecord.period_start <= VehiclePause.pause_start,
            PaymentRecord.period_end >= VehiclePause.pause_end
        )
    ).first()
    if pause:
        return {
            "status": "暂停",
            "status_start": pause.pause_start.isoformat(),
            "status_end": pause.pause_end.isoformat(),
            "detail": f"暂停中（{pause.pause_start}~{pause.pause_end}）"
        }
    
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
            "detail": "已登记免缴费" if vehicle.is_garage else "已登记未缴费"
        }
    
    paid_to = max(p.period_end for p in vehicle.payments)
    latest_payment = [p for p in vehicle.payments if p.period_end == paid_to][0]
    
    days_past = (today - paid_to).days
    
    if paid_to >= today:
        return {
            "status": "合约",
            "status_start": latest_payment.period_start.isoformat(),
            "status_end": paid_to.isoformat(),
            "detail": f"合约至{paid_to.strftime('%Y-%m-%d')}"
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

def calculate_payment_amount(vehicle, period_type, months, db, pause_months=0):
    if vehicle.is_garage:
        return {"amount": 0, "base_amount": 0, "discount_amount": 0, "summary": "车库车 - 无需缴费", "tier": None, "discount": None}
    
    tier = get_applicable_fee_tier(vehicle, db)
    discount = get_applicable_discount(vehicle, db)
    
    if not tier:
        return {"amount": 0, "base_amount": 0, "discount_amount": 0, "summary": "未找到适用档位", "tier": None, "discount": None}
    
    paid_months = max(0, months - pause_months)
    if paid_months == 0:
        return {"amount": 0, "base_amount": 0, "discount_amount": 0, "summary": "暂停月数等于缴费月数，无需缴费", "tier": None, "discount": None}
    
    period_months = paid_months
    if period_type == "包季":
        period_months = paid_months * 3
    elif period_type == "包年":
        period_months = paid_months * 12
    
    monthly_fee = float(tier.monthly_fee)
    
    if period_type == "包月":
        base_amount = monthly_fee * paid_months
    elif period_type == "包季":
        if tier.quarterly_fee:
            base_amount = float(tier.quarterly_fee) * paid_months
        else:
            base_amount = monthly_fee * 3 * paid_months
    elif period_type == "包年":
        if tier.yearly_fee:
            base_amount = float(tier.yearly_fee) * paid_months
        else:
            base_amount = monthly_fee * 12 * paid_months
    else:
        base_amount = monthly_fee * paid_months
    
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
    
    total_months = months
    if period_type == "包季":
        total_months = months * 3
    elif period_type == "包年":
        total_months = months * 12
    summary_parts = [f"第{vehicle.sort_order}辆车 {monthly_fee}元/月 × {period_months}个月（总{total_months}个月，暂停{pause_months}个月） = {base_amount:.2f}元"]
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
    :param area: 区域（如 "之荣径"）
    :param building: 楼号（如 "8"）
    :param unit: 单元号（如 "1"，可为空）
    :param room: 房间号（如 "202"）
    :param db: 数据库会话
    :return: 格式化的房号
    """
    # 清理输入
    area = area.strip() if area else ""
    building = building.strip() if building else ""
    unit = unit.strip() if unit else ""
    room = room.strip() if room else ""
    
    # 默认规则
    default_rules = [
        {"area_example": "之荣径", "area_optional": False, "building_example": "8", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "202", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "之荣径", "area_optional": False, "building_example": "1", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "", "room_optional": True, "format": "{area}{building}号"},
        {"area_example": "之泰径", "area_optional": False, "building_example": "5", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "502", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "", "area_optional": True, "building_example": "2", "building_optional": False, "unit_example": "3", "unit_optional": False, "room_example": "602", "room_optional": False, "format": "{building}-{unit}-{room}"},
        {"area_example": "", "area_optional": True, "building_example": "3", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "101", "room_optional": False, "format": "{building}号{room}"}
    ]
    
    # 获取格式规则
    patterns_str = get_system_setting(db, "room_format_patterns", "")
    
    rules = default_rules
    if patterns_str:
        try:
            parsed_rules = json.loads(patterns_str)
            if isinstance(parsed_rules, list) and len(parsed_rules) > 0:
                rules = parsed_rules
        except (json.JSONDecodeError, TypeError):
            rules = default_rules
    
    # 按优先级匹配规则
    for rule in rules:
        # 解析规则条件
        area_opt = rule.get("area_optional", False)
        building_opt = rule.get("building_optional", False)
        unit_opt = rule.get("unit_optional", True)
        room_opt = rule.get("room_optional", False)
        format_str = rule.get("format", "")
        
        if not format_str:
            continue
        
        # 检查区域字段
        if area_opt and area:
            continue  # 规则要求不填区域，但实际填了
        if not area_opt and not area:
            continue  # 规则要求填区域，但实际没填
        
        # 检查楼号字段
        if building_opt and building:
            continue  # 规则要求不填楼号，但实际填了
        if not building_opt and not building:
            continue  # 规则要求填楼号，但实际没填
        
        # 检查单元号字段
        if unit_opt and unit:
            continue  # 规则要求不填单元号，但实际填了
        if not unit_opt and not unit:
            continue  # 规则要求填单元号，但实际没填
        
        # 检查房间号字段
        if room_opt and room:
            continue  # 规则要求不填房间号，但实际填了
        if not room_opt and not room:
            continue  # 规则要求填房间号，但实际没填
        
        # 找到匹配的规则！现在用实际值替换占位符
        result = format_str
        if area:
            result = result.replace("{area}", area)
        if building:
            result = result.replace("{building}", building)
        if unit:
            result = result.replace("{unit}", unit)
        if room:
            result = result.replace("{room}", room)
        
        # 清理多余的占位符
        result = result.replace("{area}", "").replace("{building}", "").replace("{unit}", "").replace("{room}", "")
        
        if result:
            return result
    
    # 默认格式
    if building:
        if area and unit and room:
            return f"{area}{building}幢{unit}单元{room}室"
        elif area and room:
            return f"{area}{building}号{room}"
        elif unit and room:
            return f"{building}-{unit}-{room}"
        elif room:
            return f"{building}号{room}"
        else:
            return f"{area}{building}号"
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

def validate_plate_number(plate: str) -> tuple[bool, str]:
    if not plate or not plate.strip():
        return False, "车牌号不能为空"
    cleaned = plate.strip().upper().replace("·", "").replace("-", "").replace(" ", "")
    if len(cleaned) < 6:
        return False, "车牌号格式无效（长度过短）"
    if len(cleaned) > 10:
        return False, "车牌号格式无效（长度过长）"
    first = cleaned[0]
    if not ('\u4e00' <= first <= '\u9fff'):
        if not cleaned.startswith("WJ"):
            return False, "车牌号应以汉字开头"
    for ch in cleaned:
        if not ('\u4e00' <= ch <= '\u9fff') and not ('A' <= ch <= 'Z') and not ('0' <= ch <= '9'):
            return False, "车牌号包含非法字符"
    return True, ""

def check_period_overlap(vehicle_id, new_start, new_end, db):
    existing = db.query(PaymentRecord).filter(
        PaymentRecord.vehicle_id == vehicle_id,
        PaymentRecord.period_start <= new_end,
        PaymentRecord.period_end >= new_start
    ).order_by(PaymentRecord.period_start).all()
    warnings = []
    for p in existing:
        paused = db.query(VehiclePause).filter(
            VehiclePause.payment_id == p.id,
            VehiclePause.pause_start <= new_end,
            VehiclePause.pause_end >= new_start
        ).first()
        if not paused:
            warnings.append(f"与已有缴费记录 {p.period_start}~{p.period_end} 重叠")
    return warnings
