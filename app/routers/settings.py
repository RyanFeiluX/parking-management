from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json

from ..models import SystemSetting, OperationLog
from ..deps import require_role

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

def get_or_create_setting(db: Session, key: str, default_value: str, description: str = ""):
    setting = db.query(SystemSetting).filter_by(key=key).first()
    if not setting:
        setting = SystemSetting(key=key, value=default_value, description=description)
        db.add(setting)
        db.commit()
    return setting

@router.get("/")
async def basic_settings_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    
    grace_period = get_or_create_setting(db, "grace_period_days", "15", "车辆过期宽限期(天)")
    company_name = get_or_create_setting(db, "company_name", "小区停车管理系统", "系统标题")
    area_options = get_or_create_setting(db, "area_options", "之荣径,之泰径", "区域选项，多个选项用逗号分隔")
    
    # 默认规则
    default_rules = [
        {"area_example": "之荣径", "area_optional": False, "building_example": "8", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "202", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "之荣径", "area_optional": False, "building_example": "1", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "", "room_optional": True, "format": "{area}{building}号"},
        {"area_example": "之泰径", "area_optional": False, "building_example": "5", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "502", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "", "area_optional": True, "building_example": "2", "building_optional": False, "unit_example": "3", "unit_optional": False, "room_example": "602", "room_optional": False, "format": "{building}-{unit}-{room}"},
        {"area_example": "", "area_optional": True, "building_example": "3", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "101", "room_optional": False, "format": "{building}号{room}"}
    ]
    
    room_format_patterns = get_or_create_setting(db, "room_format_patterns", json.dumps(default_rules), "房号格式规则")
    
    # 尝试解析现有规则
    try:
        rules_json = json.loads(room_format_patterns.value)
        if not isinstance(rules_json, list):
            rules_json = default_rules
    except (json.JSONDecodeError, TypeError):
        rules_json = default_rules
    
    return templates.TemplateResponse("settings/basic.html", {
        "request": request,
        "current_user": user,
        "grace_period": grace_period,
        "company_name": company_name,
        "area_options": area_options,
        "room_format_patterns": room_format_patterns,
        "rules_json_str": json.dumps(rules_json),
        "success": None
    })


@router.get("/temp-rules")
async def temp_rules_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    
    temp_rules = get_or_create_setting(db, "temp_parking_rules", '{"free_minutes": 30, "daily_cap": 20.00, "tiers": [{"from_hours": 0, "to_hours": 1, "fee": 0}, {"from_hours": 1, "to_hours": 2, "fee": 5}, {"from_hours": 2, "to_hours": 12, "fee": 10}, {"from_hours": 12, "to_hours": 24, "fee": 20}], "overflow": "daily_reset"}', "临时停车费率规则")
    
    try:
        rules_data = json.loads(temp_rules.value)
    except json.JSONDecodeError:
        rules_data = {"free_minutes": 30, "daily_cap": 20.00, "tiers": [], "overflow": "daily_reset"}
    
    return templates.TemplateResponse("settings/temp-rules.html", {
        "request": request,
        "current_user": user,
        "temp_rules": rules_data or {},
        "overflow_options": ["daily_reset", "continue"],
        "success": None
    })


@router.get("/external-api")
async def external_api_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    
    api_token = get_or_create_setting(db, "api_token", "", "外部API访问令牌")
    
    return templates.TemplateResponse("settings/external-api.html", {
        "request": request,
        "current_user": user,
        "api_token": api_token,
        "success": None
    })


@router.post("/save-external-api")
async def save_external_api(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    
    db = request.state.db
    
    api_token = get_or_create_setting(db, "api_token", "")
    api_token.value = form_data.get("api_token", "")
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "system_backup", "外部接口配置", "更新外部接口配置", client_host)
    
    return templates.TemplateResponse("settings/external-api.html", {
        "request": request,
        "current_user": user,
        "api_token": api_token,
        "success": "外部接口配置已更新"
    })

@router.post("/save")
async def save_settings(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    
    db = request.state.db
    
    # 默认规则
    default_rules = [
        {"area_example": "之荣径", "area_optional": False, "building_example": "8", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "202", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "之荣径", "area_optional": False, "building_example": "1", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "", "room_optional": True, "format": "{area}{building}号"},
        {"area_example": "之泰径", "area_optional": False, "building_example": "5", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "502", "room_optional": False, "format": "{area}{building}号{room}"},
        {"area_example": "", "area_optional": True, "building_example": "2", "building_optional": False, "unit_example": "3", "unit_optional": False, "room_example": "602", "room_optional": False, "format": "{building}-{unit}-{room}"},
        {"area_example": "", "area_optional": True, "building_example": "3", "building_optional": False, "unit_example": "", "unit_optional": True, "room_example": "101", "room_optional": False, "format": "{building}号{room}"}
    ]
    
    # 获取并验证房号格式规则
    room_format_patterns_value = form_data.get("room_format_patterns", "")
    # 如果是空值，使用默认规则
    if not room_format_patterns_value or room_format_patterns_value.strip() == "":
        room_format_patterns_value = json.dumps(default_rules)
    
    # 验证JSON格式是否有效
    try:
        rules_json = json.loads(room_format_patterns_value)
        if not isinstance(rules_json, list):
            rules_json = default_rules
            room_format_patterns_value = json.dumps(default_rules)
    except (json.JSONDecodeError, TypeError):
        rules_json = default_rules
        room_format_patterns_value = json.dumps(default_rules)
    
    # 保存各个设置
    grace_period = get_or_create_setting(db, "grace_period_days", "15")
    grace_period.value = form_data.get("grace_period_days", "15")
    
    company_name = get_or_create_setting(db, "company_name", "")
    company_name.value = form_data.get("company_name", "")
    
    area_options = get_or_create_setting(db, "area_options", "之荣径,之泰径")
    area_options.value = form_data.get("area_options", "之荣径,之泰径")
    
    room_format_patterns = get_or_create_setting(db, "room_format_patterns", json.dumps(default_rules))
    room_format_patterns.value = room_format_patterns_value
    
    # 一次性提交所有修改
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "system_backup", "系统设置", "更新系统设置", client_host)
    
    return templates.TemplateResponse("settings/basic.html", {
        "request": request,
        "current_user": user,
        "grace_period": grace_period,
        "company_name": company_name,
        "area_options": area_options,
        "room_format_patterns": room_format_patterns,
        "rules_json_str": json.dumps(rules_json),
        "success": "系统设置已更新"
    })

@router.post("/save-temp-rules")
async def save_temp_rules(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    
    free_minutes = int(form_data.get("free_minutes", 30))
    daily_cap = float(form_data.get("daily_cap", 20))
    overflow = form_data.get("overflow", "daily_reset")
    rate_type = form_data.get("rate_type", "tier")
    
    rules = {
        "free_minutes": free_minutes,
        "daily_cap": daily_cap,
        "overflow": overflow,
        "rate_type": rate_type
    }
    
    if rate_type == "tier":
        tiers = []
        i = 0
        while True:
            from_hours = form_data.get(f"tier_{i}_from")
            to_hours = form_data.get(f"tier_{i}_to")
            fee = form_data.get(f"tier_{i}_fee")
            if not from_hours or not to_hours or not fee:
                break
            tiers.append({
                "from_hours": int(from_hours),
                "to_hours": int(to_hours),
                "fee": float(fee)
            })
            i += 1
        rules["tiers"] = tiers
    else:
        rules["flat_interval"] = int(form_data.get("flat_interval", 30))
        rules["flat_rate"] = float(form_data.get("flat_rate", 5.0))
        rules["tiers"] = []
    
    db = request.state.db
    temp_rules = get_or_create_setting(db, "temp_parking_rules", "")
    temp_rules.value = json.dumps(rules)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "system_backup", "临时停车规则", "更新临时停车费率规则", client_host)
    
    return templates.TemplateResponse("settings/temp-rules.html", {
        "request": request,
        "current_user": user,
        "temp_rules": rules,
        "overflow_options": ["daily_reset", "continue"],
        "success": "临时停车规则已更新"
    })
