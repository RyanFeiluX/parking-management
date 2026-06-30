from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
import json

from ..models import Invoice, PaymentRecord, Vehicle, Resident, User, OperationLog, SystemSetting
from ..deps import require_role, require_login

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
async def invoice_list(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    status_filter = request.query_params.get("status", "")
    invoice_type_filter = request.query_params.get("invoice_type", "")
    plate_number = request.query_params.get("plate_number", "")
    start_date = request.query_params.get("start_date", "")
    end_date = request.query_params.get("end_date", "")

    query = db.query(Invoice).order_by(Invoice.created_at.desc())

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if invoice_type_filter:
        query = query.filter(Invoice.invoice_type == invoice_type_filter)
    if start_date:
        query = query.filter(Invoice.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(Invoice.created_at <= datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1))
    if plate_number:
        query = query.join(PaymentRecord).join(Vehicle).filter(Vehicle.plate_number.ilike(f"%{plate_number}%"))

    invoices = query.all()

    invoice_data = []
    for inv in invoices:
        payment = inv.payment
        vehicle = payment.vehicle if payment else None
        resident = vehicle.resident if vehicle else None
        operator = db.query(User).filter_by(id=payment.operator_id).first() if payment and payment.operator_id else None
        invoice_data.append({
            "invoice": inv,
            "payment": payment,
            "vehicle": vehicle,
            "resident": resident,
            "operator": operator
        })

    return templates.TemplateResponse("invoices/list.html", {
        "request": request,
        "current_user": user,
        "invoices": invoice_data,
        "status_filter": status_filter,
        "invoice_type_filter": invoice_type_filter,
        "plate_number": plate_number,
        "start_date": start_date,
        "end_date": end_date
    })

@router.get("/create")
async def create_invoice_page(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    payment_id = request.query_params.get("payment_id")
    error = None

    payment = None
    if payment_id:
        payment = db.query(PaymentRecord).filter_by(id=int(payment_id)).first()
        if not payment:
            error = "交费记录不存在"
        elif payment.invoice:
            error = "该交费记录已关联开票条目"

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
            if not isinstance(presets, list):
                presets = []
        except (json.JSONDecodeError, TypeError):
            presets = []

    return templates.TemplateResponse("invoices/form.html", {
        "request": request,
        "current_user": user,
        "payment": payment,
        "presets": presets,
        "error": error
    })

@router.post("/create")
async def create_invoice(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    payment_id = int(form_data.get("payment_id"))
    title = form_data.get("title", "").strip()
    tax_id = form_data.get("tax_id", "").strip() or None
    summary = form_data.get("summary", "").strip() or None
    invoice_type = form_data.get("invoice_type", "普票")
    amount = float(form_data.get("amount", 0))

    db = request.state.db
    payment = db.query(PaymentRecord).filter_by(id=payment_id).first()
    if not payment:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "error": "交费记录不存在"
        })
    if payment.invoice:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "error": "该交费记录已关联开票条目"
        })
    if not title:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "payment": payment, "error": "发票抬头不能为空"
        })
    if amount <= 0:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "payment": payment, "error": "发票金额必须大于0"
        })

    invoice = Invoice(
        payment_id=payment_id,
        title=title,
        tax_id=tax_id,
        summary=summary,
        invoice_type=invoice_type,
        amount=amount,
        status="开票等待中"
    )
    db.add(invoice)
    db.commit()

    vehicle = payment.vehicle
    target = f"车辆 {vehicle.plate_number}" if vehicle else f"交费 #{payment_id}"
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "create_invoice", target,
                  f"创建开票申请: {title}, {amount}元, {invoice_type}", client_host)

    return templates.TemplateResponse("invoices/form.html", {
        "request": request, "current_user": user,
        "success": "开票申请已提交", "payment": payment
    })

@router.get("/{invoice_id}/edit")
async def edit_invoice_page(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })

    if invoice.status != "开票等待中":
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": db.query(Invoice).all(), "error": "仅开票等待中的记录可编辑"
        })

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            presets = []

    return templates.TemplateResponse("invoices/form.html", {
        "request": request, "current_user": user,
        "invoice": invoice, "payment": invoice.payment, "presets": presets
    })

@router.post("/{invoice_id}/edit")
async def edit_invoice(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    form_data = await request.form()
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })
    if invoice.status != "开票等待中":
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": db.query(Invoice).all(), "error": "仅开票等待中的记录可编辑"
        })

    title = form_data.get("title", "").strip()
    if not title:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "invoice": invoice, "error": "发票抬头不能为空"
        })

    invoice.title = title
    invoice.tax_id = form_data.get("tax_id", "").strip() or None
    invoice.summary = form_data.get("summary", "").strip() or None
    invoice.invoice_type = form_data.get("invoice_type", "普票")
    invoice.amount = float(form_data.get("amount", 0))
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_invoice", f"开票 #{invoice_id}",
                  f"更新开票信息: {invoice.title}, {invoice.amount}元", client_host)

    return templates.TemplateResponse("invoices/form.html", {
        "request": request, "current_user": user, "invoice": invoice,
        "payment": invoice.payment, "success": "开票信息已更新"
    })

@router.post("/{invoice_id}/complete")
async def complete_invoice(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })
    if invoice.status != "开票等待中":
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": db.query(Invoice).all(), "error": "仅开票等待中的记录可标记完成"
        })

    invoice.status = "开票已完成"
    invoice.completed_at = datetime.now()
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "complete_invoice", f"开票 #{invoice_id}",
                  f"开票完成: {invoice.title}, {invoice.amount}元", client_host)

    return templates.TemplateResponse("invoices/list.html", {
        "request": request, "current_user": user,
        "invoices": build_invoice_data(db, db.query(Invoice).order_by(Invoice.created_at.desc()).all()),
        "success": "开票已标记完成"
    })

@router.post("/{invoice_id}/cancel")
async def cancel_invoice(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })
    if invoice.status != "开票等待中":
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": db.query(Invoice).all(), "error": "仅开票等待中的记录可取消"
        })

    invoice.status = "申请已取消"
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "cancel_invoice", f"开票 #{invoice_id}",
                  f"取消开票申请: {invoice.title}", client_host)

    return templates.TemplateResponse("invoices/list.html", {
        "request": request, "current_user": user,
        "invoices": build_invoice_data(db, db.query(Invoice).order_by(Invoice.created_at.desc()).all()),
        "success": "开票申请已取消"
    })

def build_invoice_data(db, invoices):
    data = []
    for inv in invoices:
        payment = inv.payment
        vehicle = payment.vehicle if payment else None
        resident = vehicle.resident if vehicle else None
        operator = db.query(User).filter_by(id=payment.operator_id).first() if payment and payment.operator_id else None
        data.append({
            "invoice": inv,
            "payment": payment,
            "vehicle": vehicle,
            "resident": resident,
            "operator": operator
        })
    return data
