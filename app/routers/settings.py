import os
import json
from pathlib import Path
from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session

from ..models import SystemSetting, OperationLog, Resident, Vehicle, PaymentRecord, User
from ..deps import require_role
from ..jinja import templates
from .._path import get_db_path, get_config_path, load_config, save_config, get_user_data_dir

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
    community_address = get_or_create_setting(db, "community_address", "", "小区地址（开票备注中使用）")
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
        "community_address": community_address,
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

    community_address = get_or_create_setting(db, "community_address", "")
    community_address.value = form_data.get("community_address", "")

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
        "community_address": community_address,
        "area_options": area_options,
        "room_format_patterns": room_format_patterns,
        "rules_json_str": json.dumps(rules_json),
        "success": "系统设置已更新"
    })

def normalize_presets(presets):
    """兼容旧格式 ['Title'] → 新格式 [{'title':'Title','tax_id':'','phone':'','email':'','address':'','bank_name':'','bank_account':''}]"""
    normalized = []
    for p in presets:
        if isinstance(p, str):
            normalized.append({"title": p, "tax_id": "", "phone": "", "email": "", "address": "", "bank_name": "", "bank_account": ""})
        elif isinstance(p, dict):
            normalized.append({
                "title": p.get("title", ""),
                "tax_id": p.get("tax_id", ""),
                "phone": p.get("phone", ""),
                "email": p.get("email", ""),
                "address": p.get("address", ""),
                "bank_name": p.get("bank_name", ""),
                "bank_account": p.get("bank_account", "")
            })
    return normalized

@router.get("/invoice-titles")
async def invoice_titles_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db
    setting = get_or_create_setting(db, "invoice_title_presets", "[]", "发票抬头预设列表（JSON数组）")

    try:
        titles = json.loads(setting.value)
        if not isinstance(titles, list):
            titles = []
        titles = normalize_presets(titles)
    except (json.JSONDecodeError, TypeError):
        titles = []

    return templates.TemplateResponse("settings/invoice-titles.html", {
        "request": request,
        "current_user": user,
        "titles": titles,
        "titles_json": json.dumps(titles, ensure_ascii=False),
        "success": None
    })

@router.post("/save-invoice-titles")
async def save_invoice_titles(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    titles_raw = form_data.get("titles", "[]")

    try:
        titles = json.loads(titles_raw)
        if not isinstance(titles, list):
            titles = []
    except (json.JSONDecodeError, TypeError):
        titles = []

    db = request.state.db
    setting = get_or_create_setting(db, "invoice_title_presets", "[]")
    setting.value = json.dumps(titles)
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "system_backup", "发票抬头预设", "更新发票抬头预设列表", client_host)

    return templates.TemplateResponse("settings/invoice-titles.html", {
        "request": request,
        "current_user": user,
        "titles": titles,
        "titles_json": json.dumps(titles),
        "success": "发票抬头预设已更新"
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

@router.get("/database")
async def database_settings_page(request: Request, user: dict = Depends(require_role("super_admin"))):
    db = request.state.db

    config = load_config()
    default_db_path = str(get_db_path())
    actual_db_path = str(Path(db.get_bind().url.database)) if db.get_bind().url.database else default_db_path

    db_file_size = 0
    if os.path.exists(actual_db_path):
        db_file_size = os.path.getsize(actual_db_path)

    resident_count = db.query(Resident).count()
    vehicle_count = db.query(Vehicle).count()
    payment_count = db.query(PaymentRecord).count()
    user_count = db.query(User).count()

    return templates.TemplateResponse("settings/database.html", {
        "request": request,
        "current_user": user,
        "default_db_path": default_db_path,
        "actual_db_path": actual_db_path,
        "config_db_path": config.get('db_path', ''),
        "config_path": str(get_config_path()),
        "data_dir": str(get_user_data_dir()),
        "db_file_size": db_file_size,
        "resident_count": resident_count,
        "vehicle_count": vehicle_count,
        "payment_count": payment_count,
        "user_count": user_count,
        "success": None
    })

@router.post("/database/save")
async def save_database_config(request: Request, user: dict = Depends(require_role("super_admin"))):
    form_data = await request.form()
    new_db_path = form_data.get("db_path", "").strip()

    config = load_config()
    if new_db_path:
        config['db_path'] = new_db_path
    else:
        config.pop('db_path', None)
        config.pop('db_url', None)
    save_config(config)

    db = request.state.db
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "system_database", "数据库配置", f"切换数据库路径: {new_db_path or '默认'}", client_host)

    return templates.TemplateResponse("settings/database.html", {
        "request": request,
        "current_user": user,
        "default_db_path": str(get_db_path()),
        "actual_db_path": str(get_db_path()),
        "config_db_path": new_db_path,
        "config_path": str(get_config_path()),
        "data_dir": str(get_user_data_dir()),
        "db_file_size": 0,
        "resident_count": 0,
        "vehicle_count": 0,
        "payment_count": 0,
        "user_count": 0,
        "success": "配置已保存，请手动重启应用以使新数据库路径生效"
    })
