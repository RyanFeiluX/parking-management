from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from datetime import datetime, date

from ..models import DiscountPolicy, OperationLog
from ..deps import require_role
from ..jinja import templates

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

@router.get("/")
async def list_discounts(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    show_history = request.query_params.get("show_history", "false") == "true"
    
    if show_history:
        discounts = db.query(DiscountPolicy).order_by(DiscountPolicy.effective_date.desc()).all()
    else:
        discounts = db.query(DiscountPolicy).filter_by(expired_at=None).all()
    
    return templates.TemplateResponse("discounts/list.html", {
        "request": request,
        "current_user": user,
        "discounts": discounts,
        "show_history": show_history
    })

@router.get("/add")
async def add_discount_page(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    today = date.today()
    return templates.TemplateResponse("discounts/form.html", {
        "request": request,
        "current_user": user,
        "today": today.isoformat(),
        "discount_types": ["discount_percent", "free", "fixed_fee"],
        "scope_types": ["vehicle_type", "room_prefix", "all"]
    })

@router.post("/add")
async def add_discount(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    name = form_data.get("name")
    discount_type = form_data.get("discount_type")
    discount_value = float(form_data.get("discount_value"))
    scope_type = form_data.get("scope_type")
    scope_value = form_data.get("scope_value")
    apply_seq_from = int(form_data.get("apply_seq_from", 1))
    apply_seq_to = int(form_data.get("apply_seq_to", 999))
    effective_date = date.fromisoformat(form_data.get("effective_date"))
    
    today = date.today()
    if effective_date < today:
        return templates.TemplateResponse("discounts/form.html", {
            "request": request,
            "current_user": user,
            "today": today.isoformat(),
            "discount_types": ["discount_percent", "free", "fixed_fee"],
            "scope_types": ["vehicle_type", "room_prefix", "all"],
            "error": "生效日期不能早于今天"
        })
    
    db = request.state.db
    
    discount = DiscountPolicy(
        name=name,
        discount_type=discount_type,
        discount_value=discount_value,
        scope_type=scope_type,
        scope_value=scope_value,
        apply_seq_from=apply_seq_from,
        apply_seq_to=apply_seq_to,
        effective_date=effective_date
    )
    db.add(discount)
    db.commit()
    
    log_operation(db, user["user_id"], "create_discount", f"优惠策略 {name}", f"新增优惠策略", request.client.host)
    
    return templates.TemplateResponse("discounts/list.html", {
        "request": request,
        "current_user": user,
        "discounts": db.query(DiscountPolicy).filter_by(expired_at=None).all(),
        "success": "优惠策略添加成功"
    })

@router.get("/{discount_id}/edit")
async def edit_discount_page(request: Request, discount_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    discount = db.query(DiscountPolicy).filter_by(id=discount_id).first()
    
    if not discount:
        return templates.TemplateResponse("discounts/list.html", {
            "request": request,
            "current_user": user,
            "discounts": db.query(DiscountPolicy).filter_by(expired_at=None).all(),
            "error": "优惠策略不存在"
        })
    
    today = date.today()
    return templates.TemplateResponse("discounts/form.html", {
        "request": request,
        "current_user": user,
        "discount": discount,
        "today": today.isoformat(),
        "discount_types": ["discount_percent", "free", "fixed_fee"],
        "scope_types": ["vehicle_type", "room_prefix", "all"]
    })

@router.post("/{discount_id}/edit")
async def edit_discount(request: Request, discount_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    name = form_data.get("name")
    discount_type = form_data.get("discount_type")
    discount_value = float(form_data.get("discount_value"))
    scope_type = form_data.get("scope_type")
    scope_value = form_data.get("scope_value")
    apply_seq_from = int(form_data.get("apply_seq_from", 1))
    apply_seq_to = int(form_data.get("apply_seq_to", 999))
    effective_date = date.fromisoformat(form_data.get("effective_date"))
    
    today = date.today()
    if effective_date < today:
        return templates.TemplateResponse("discounts/form.html", {
            "request": request,
            "current_user": user,
            "today": today.isoformat(),
            "discount_types": ["discount_percent", "free", "fixed_fee"],
            "scope_types": ["vehicle_type", "room_prefix", "all"],
            "error": "生效日期不能早于今天"
        })
    
    db = request.state.db
    old_discount = db.query(DiscountPolicy).filter_by(id=discount_id).first()
    
    if not old_discount:
        return templates.TemplateResponse("discounts/list.html", {
            "request": request,
            "current_user": user,
            "discounts": db.query(DiscountPolicy).filter_by(expired_at=None).all(),
            "error": "优惠策略不存在"
        })
    
    old_discount.expired_at = datetime.now()
    
    new_discount = DiscountPolicy(
        name=name,
        discount_type=discount_type,
        discount_value=discount_value,
        scope_type=scope_type,
        scope_value=scope_value,
        apply_seq_from=apply_seq_from,
        apply_seq_to=apply_seq_to,
        effective_date=effective_date
    )
    db.add(new_discount)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_discount", f"优惠策略 {name}", "更新优惠策略", client_host)
    
    return templates.TemplateResponse("discounts/list.html", {
        "request": request,
        "current_user": user,
        "discounts": db.query(DiscountPolicy).filter_by(expired_at=None).all(),
        "success": "优惠策略已更新（创建新版本）"
    })