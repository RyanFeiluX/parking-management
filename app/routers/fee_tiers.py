from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, date

from ..models import FeeTier, OperationLog
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

@router.get("/")
async def list_fee_tiers(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    show_history = request.query_params.get("show_history", "false") == "true"
    
    if show_history:
        tiers = db.query(FeeTier).order_by(FeeTier.seq_from, FeeTier.effective_date.desc()).all()
    else:
        tiers = db.query(FeeTier).filter_by(expired_at=None).order_by(FeeTier.seq_from).all()
    
    return templates.TemplateResponse("fee_tiers/list.html", {
        "request": request,
        "current_user": user,
        "tiers": tiers,
        "show_history": show_history
    })

@router.get("/add")
async def add_fee_tier_page(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    today = date.today()
    return templates.TemplateResponse("fee_tiers/form.html", {
        "request": request,
        "current_user": user,
        "today": today.isoformat()
    })

@router.post("/add")
async def add_fee_tier(request: Request, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    seq_from = int(form_data.get("seq_from"))
    seq_to = int(form_data.get("seq_to"))
    monthly_fee = float(form_data.get("monthly_fee"))
    quarterly_fee = float(form_data.get("quarterly_fee")) if form_data.get("quarterly_fee") else None
    yearly_fee = float(form_data.get("yearly_fee")) if form_data.get("yearly_fee") else None
    effective_date = date.fromisoformat(form_data.get("effective_date"))
    
    today = date.today()
    if effective_date < today:
        return templates.TemplateResponse("fee_tiers/form.html", {
            "request": request,
            "current_user": user,
            "today": today.isoformat(),
            "error": "生效日期不能早于今天"
        })
    
    db = request.state.db
    
    existing = db.query(FeeTier).filter(
        FeeTier.seq_from <= seq_to,
        FeeTier.seq_to >= seq_from,
        FeeTier.expired_at.is_(None)
    ).first()
    
    if existing:
        return templates.TemplateResponse("fee_tiers/form.html", {
            "request": request,
            "current_user": user,
            "today": today.isoformat(),
            "error": f"序号范围 {seq_from}~{seq_to} 与现有档位重叠"
        })
    
    tier = FeeTier(
        seq_from=seq_from,
        seq_to=seq_to,
        monthly_fee=monthly_fee,
        quarterly_fee=quarterly_fee,
        yearly_fee=yearly_fee,
        effective_date=effective_date
    )
    db.add(tier)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_fee_tier", f"档位 {seq_from}-{seq_to}", f"新增档位: 月费{monthly_fee}元，生效{effective_date}", client_host)
    
    return templates.TemplateResponse("fee_tiers/list.html", {
        "request": request,
        "current_user": user,
        "tiers": db.query(FeeTier).filter_by(expired_at=None).order_by(FeeTier.seq_from).all(),
        "success": "档位规则添加成功"
    })

@router.get("/{tier_id}/edit")
async def edit_fee_tier_page(request: Request, tier_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    db = request.state.db
    tier = db.query(FeeTier).filter_by(id=tier_id).first()
    
    if not tier:
        return templates.TemplateResponse("fee_tiers/list.html", {
            "request": request,
            "current_user": user,
            "tiers": db.query(FeeTier).filter_by(expired_at=None).order_by(FeeTier.seq_from).all(),
            "error": "档位不存在"
        })
    
    today = date.today()
    return templates.TemplateResponse("fee_tiers/form.html", {
        "request": request,
        "current_user": user,
        "tier": tier,
        "today": today.isoformat()
    })

@router.post("/{tier_id}/edit")
async def edit_fee_tier(request: Request, tier_id: int, user: dict = Depends(require_role("admin", "super_admin"))):
    form_data = await request.form()
    seq_from = int(form_data.get("seq_from"))
    seq_to = int(form_data.get("seq_to"))
    monthly_fee = float(form_data.get("monthly_fee"))
    quarterly_fee = float(form_data.get("quarterly_fee")) if form_data.get("quarterly_fee") else None
    yearly_fee = float(form_data.get("yearly_fee")) if form_data.get("yearly_fee") else None
    effective_date = date.fromisoformat(form_data.get("effective_date"))
    
    today = date.today()
    if effective_date < today:
        return templates.TemplateResponse("fee_tiers/form.html", {
            "request": request,
            "current_user": user,
            "today": today.isoformat(),
            "error": "生效日期不能早于今天"
        })
    
    db = request.state.db
    old_tier = db.query(FeeTier).filter_by(id=tier_id).first()
    
    if not old_tier:
        return templates.TemplateResponse("fee_tiers/list.html", {
            "request": request,
            "current_user": user,
            "tiers": db.query(FeeTier).filter_by(expired_at=None).order_by(FeeTier.seq_from).all(),
            "error": "档位不存在"
        })
    
    old_tier.expired_at = datetime.now()
    
    new_tier = FeeTier(
        seq_from=seq_from,
        seq_to=seq_to,
        monthly_fee=monthly_fee,
        quarterly_fee=quarterly_fee,
        yearly_fee=yearly_fee,
        effective_date=effective_date
    )
    db.add(new_tier)
    db.commit()
    
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_fee_tier", f"档位 {seq_from}-{seq_to}", f"更新档位: {old_tier.monthly_fee}元 → {monthly_fee}元，生效{effective_date}", client_host)
    
    return templates.TemplateResponse("fee_tiers/list.html", {
        "request": request,
        "current_user": user,
        "tiers": db.query(FeeTier).filter_by(expired_at=None).order_by(FeeTier.seq_from).all(),
        "success": "档位规则已更新（创建新版本）"
    })