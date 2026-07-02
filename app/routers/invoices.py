from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import csv
import io
import json
from urllib.parse import quote

from ..models import Invoice, PaymentRecord, Vehicle, Resident, User, OperationLog, SystemSetting, VehiclePause
from ..deps import require_role, require_login
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

def build_invoice_summary(payments, db=None):
    if not payments:
        return ""
    plate = payments[0].vehicle.plate_number if payments[0].vehicle else ""
    if len(payments) == 1:
        p = payments[0]
        pause_desc = _get_pause_desc(p, db)
        return f"{plate} {p.period_type}缴 {p.period_start.strftime('%Y-%m-%d')}~{p.period_end.strftime('%Y-%m-%d')}{pause_desc}"
    items = []
    for p in payments:
        plt = p.vehicle.plate_number if p.vehicle else "未知"
        pause_desc = _get_pause_desc(p, db)
        items.append(f"{plt} {p.period_type}缴{p.period_start.strftime('%Y-%m-%d')}~{p.period_end.strftime('%Y-%m-%d')}({float(p.amount):.0f}元){pause_desc}")
    total = sum(float(p.amount) for p in payments)
    return f"合并{len(payments)}笔交费：" + "、".join(items) + f"，合计{total:.0f}元"

def _get_pause_desc(payment, db):
    if not db:
        return ""
    pauses = db.query(VehiclePause).filter_by(payment_id=payment.id).all()
    if pauses:
        parts = [f"{pr.pause_start}~{pr.pause_end}" for pr in pauses]
        return "（暂停：" + "；".join(parts) + "）"
    return ""

def build_invoice_data(db, invoices):
    data = []
    for inv in invoices:
        payments = inv.payments
        first_payment = payments[0] if payments else None
        vehicle = first_payment.vehicle if first_payment else None
        resident = vehicle.resident if vehicle else None
        operator = db.query(User).filter_by(id=first_payment.operator_id).first() if first_payment and first_payment.operator_id else None
        total_paid = sum(float(p.amount) for p in payments) if payments else 0
        plates = sorted(set(p.vehicle.plate_number for p in payments if p.vehicle and p.vehicle.plate_number))
        pause_descs = {}
        for p in payments:
            pauses = db.query(VehiclePause).filter_by(payment_id=p.id).all()
            if pauses:
                parts = [f"{pr.pause_start}~{pr.pause_end}" for pr in pauses]
                pause_descs[p.id] = "（暂停：" + "；".join(parts) + "）"
        data.append({
            "invoice": inv,
            "payments": payments,
            "payment": first_payment,
            "vehicle": vehicle,
            "resident": resident,
            "operator": operator,
            "total_paid": total_paid,
            "plates": plates,
            "pause_descs": pause_descs
        })
    return data

@router.get("/")
async def invoice_list(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    status_filter = request.query_params.get("status", "")
    invoice_type_filter = request.query_params.get("invoice_type", "")
    plate_number = request.query_params.get("plate_number", "")
    start_date = request.query_params.get("start_date", "")
    end_date = request.query_params.get("end_date", "")
    success = request.query_params.get("success", "")

    query = db.query(Invoice).order_by(Invoice.created_at.desc())

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if invoice_type_filter:
        query = query.filter(Invoice.invoice_type == invoice_type_filter)
    if start_date:
        query = query.filter(Invoice.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(Invoice.created_at <= datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    if plate_number:
        query = query.join(PaymentRecord).join(Vehicle).filter(Vehicle.plate_number.ilike(f"%{plate_number}%"))

    invoices = query.all()
    invoice_data = build_invoice_data(db, invoices)

    return templates.TemplateResponse("invoices/list.html", {
        "request": request,
        "current_user": user,
        "invoices": invoice_data,
        "status_filter": status_filter,
        "invoice_type_filter": invoice_type_filter,
        "plate_number": plate_number,
        "start_date": start_date,
        "end_date": end_date,
        "success": success or None
    })

@router.get("/export")
async def export_invoices(request: Request, user: dict = Depends(require_login)):
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
        query = query.filter(Invoice.created_at <= datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    if plate_number:
        query = query.join(PaymentRecord).join(Vehicle).filter(Vehicle.plate_number.ilike(f"%{plate_number}%"))

    invoices = query.all()
    invoice_data = build_invoice_data(db, invoices)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["申请时间", "车牌号", "房号", "笔数", "缴费期间", "发票抬头", "税号", "发票编号", "电话", "邮箱", "类型", "金额", "状态"])

    for item in invoice_data:
        inv = item["invoice"]
        vehicle = item["vehicle"]
        resident = item["resident"]
        payments = item["payments"]

        if payments:
            pause_descs = item["pause_descs"]
            if len(payments) == 1:
                p = payments[0]
                period = f"{p.period_type}缴 {p.period_start.strftime('%Y-%m-%d')}~{p.period_end.strftime('%Y-%m-%d')}{pause_descs.get(p.id, '')}"
            else:
                parts = [f"{p.period_type}缴{p.period_start.strftime('%Y-%m-%d')}~{p.period_end.strftime('%Y-%m-%d')}{pause_descs.get(p.id, '')}" for p in payments]
                period = "; ".join(parts)
        else:
            period = ""

        writer.writerow([
            inv.created_at.strftime("%Y-%m-%d %H:%M") if inv.created_at else "",
            "、".join(item["plates"]) if item["plates"] else "-",
            resident.room_number if resident else "-",
            len(payments) if payments else 0,
            period,
            inv.title or "",
            inv.tax_id or "",
            inv.invoice_number or "",
            inv.phone or "",
            inv.email or "",
            inv.invoice_type or "",
            float(inv.amount) if inv.amount else 0,
            inv.status or ""
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()
    filename = f"开票清单_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([content.encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={quote(filename)}"}
    )

@router.get("/create")
async def create_invoice_page(request: Request, user: dict = Depends(require_login)):
    db = request.state.db
    payment_ids_str = request.query_params.get("payment_ids", "")
    error = None

    payments = []
    total_amount = 0
    if payment_ids_str:
        for pid_str in payment_ids_str.split(","):
            pid_str = pid_str.strip()
            if not pid_str:
                continue
            payment = db.query(PaymentRecord).filter_by(id=int(pid_str)).first()
            if not payment:
                error = f"交费记录 {pid_str} 不存在"
                break
            if payment.invoice:
                error = f"交费记录 {pid_str} 已关联开票条目"
                break
            if payment.amount <= 0:
                error = f"交费记录 {pid_str} 金额为零，不支持开票"
                break
            payments.append(payment)
            total_amount += float(payment.amount)

    if not error and len(payments) > 0:
        resident_ids = set(p.vehicle.resident_id for p in payments if p.vehicle)
        resident_ids.discard(None)
        if len(resident_ids) > 1:
            error = "选择的交费记录必须属于同一住户"
        if not error:
            vehicles = set(p.vehicle_id for p in payments)
            if len(vehicles) > 3:
                error = "一次开票申请最多包含 3 辆车的交费记录"

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
            if not isinstance(presets, list):
                presets = []
            presets = normalize_presets(presets)
        except (json.JSONDecodeError, TypeError):
            presets = []

    auto_summary = build_invoice_summary(payments, db) if payments else ""

    resident_phone = ""
    if not error and payments:
        first = payments[0]
        if first.vehicle and first.vehicle.resident:
            resident_phone = first.vehicle.resident.phone or ""

    return templates.TemplateResponse("invoices/form.html", {
        "request": request,
        "current_user": user,
        "payments": payments,
        "total_amount": total_amount,
        "auto_summary": auto_summary,
        "presets": presets,
        "presets_json": json.dumps(presets, ensure_ascii=False),
        "error": error,
        "resident_phone": resident_phone
    })

@router.post("/create")
async def create_invoice(request: Request, user: dict = Depends(require_login)):
    form_data = await request.form()
    payment_ids_str = form_data.get("payment_ids", "")
    payment_ids = [int(x) for x in payment_ids_str.split(",") if x.strip()]
    title = form_data.get("title", "").strip()
    tax_id = form_data.get("tax_id", "").strip() or None
    summary = form_data.get("summary", "").strip() or None
    invoice_type = form_data.get("invoice_type", "普票")
    amount = float(form_data.get("amount", 0))

    db = request.state.db
    payments = db.query(PaymentRecord).filter(PaymentRecord.id.in_(payment_ids)).all()

    total_amount = sum(float(p.amount) for p in payments)
    auto_summary = build_invoice_summary(payments, db)

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
            if isinstance(presets, list):
                presets = normalize_presets(presets)
        except (json.JSONDecodeError, TypeError):
            presets = []

    resident_phone = ""
    if payments:
        first = payments[0]
        if first.vehicle and first.vehicle.resident:
            resident_phone = first.vehicle.resident.phone or ""

    common_ctx = {
        "payments": payments, "total_amount": total_amount,
        "auto_summary": auto_summary, "presets": presets,
        "presets_json": json.dumps(presets, ensure_ascii=False),
        "resident_phone": resident_phone,
    }

    if len(payments) != len(payment_ids):
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": "部分交费记录不存在"
        })

    for p in payments:
        if p.invoice:
            return templates.TemplateResponse("invoices/form.html", {
                "request": request, "current_user": user, **common_ctx,
                "error": f"交费记录 #{p.id} 已关联开票条目"
            })

    vehicles = set(p.vehicle_id for p in payments)
    resident_ids = set(p.vehicle.resident_id for p in payments if p.vehicle)
    resident_ids.discard(None)
    if len(resident_ids) > 1:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": "选择的交费记录必须属于同一住户"
        })
    if len(vehicles) > 3:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": "一次开票申请最多包含 3 辆车的交费记录"
        })

    if not title:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": "发票抬头不能为空"
        })
    if amount <= 0:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": "发票金额必须大于0"
        })

    total_paid = sum(float(p.amount) for p in payments)
    if amount > total_paid:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, **common_ctx,
            "error": f"开票金额不能大于缴费总金额（{total_paid}元）"
        })

    phone = form_data.get("phone", "").strip() or None
    email = form_data.get("email", "").strip() or None
    bank_name = form_data.get("bank_name", "").strip() or None
    bank_account = form_data.get("bank_account", "").strip() or None
    address = form_data.get("address", "").strip() or None

    invoice = Invoice(
        title=title,
        tax_id=tax_id,
        phone=phone,
        email=email,
        bank_name=bank_name,
        bank_account=bank_account,
        address=address,
        summary=summary,
        invoice_type=invoice_type,
        amount=amount,
        status="开票等待中"
    )
    db.add(invoice)
    db.flush()

    for p in payments:
        p.invoice_id = invoice.id

    db.commit()

    first_payment = payments[0]
    vehicle = first_payment.vehicle
    target = f"车辆 {vehicle.plate_number}" if vehicle else f"交费 #{payment_ids[0]}"
    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "create_invoice", target,
                  f"创建开票申请: {title}, {amount}元, {invoice_type}, 合并{len(payments)}笔交费", client_host)

    return RedirectResponse(url="/invoices/?success=开票申请已提交", status_code=302)

@router.get("/{invoice_id}/edit")
async def edit_invoice_page(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })

    if invoice.status != "开票等待中":
        invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": build_invoice_data(db, invoices), "error": "仅开票等待中的记录可编辑"
        })

    payments = invoice.payments
    total_amount = sum(float(p.amount) for p in payments) if payments else 0

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
            if isinstance(presets, list):
                presets = normalize_presets(presets)
        except (json.JSONDecodeError, TypeError):
            presets = []

    return templates.TemplateResponse("invoices/form.html", {
        "request": request, "current_user": user,
        "invoice": invoice, "payments": payments, "total_amount": total_amount,
        "presets": presets, "presets_json": json.dumps(presets, ensure_ascii=False)
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
        invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": build_invoice_data(db, invoices), "error": "仅开票等待中的记录可编辑"
        })

    payments = invoice.payments
    total_amount = sum(float(p.amount) for p in payments) if payments else 0

    tax_id = form_data.get("tax_id", "").strip()

    presets = []
    setting = db.query(SystemSetting).filter_by(key="invoice_title_presets").first()
    if setting and setting.value:
        try:
            presets = json.loads(setting.value)
            if isinstance(presets, list):
                presets = normalize_presets(presets)
        except (json.JSONDecodeError, TypeError):
            presets = []

    title = form_data.get("title", "").strip()
    if not title:
        return templates.TemplateResponse("invoices/form.html", {
            "request": request, "current_user": user, "invoice": invoice,
            "payments": payments, "total_amount": total_amount,
            "presets": presets, "presets_json": json.dumps(presets, ensure_ascii=False),
            "error": "发票抬头不能为空"
        })
    invoice.title = title
    invoice.tax_id = tax_id or None
    invoice.phone = form_data.get("phone", "").strip() or None
    invoice.email = form_data.get("email", "").strip() or None
    invoice.bank_name = form_data.get("bank_name", "").strip() or None
    invoice.bank_account = form_data.get("bank_account", "").strip() or None
    invoice.address = form_data.get("address", "").strip() or None
    invoice.summary = form_data.get("summary", "").strip() or None
    invoice.invoice_type = form_data.get("invoice_type", "普票")
    invoice.amount = float(form_data.get("amount", 0))
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "update_invoice", f"开票 #{invoice_id}",
                  f"更新开票信息: {invoice.title}, {invoice.amount}元", client_host)

    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return templates.TemplateResponse("invoices/list.html", {
        "request": request, "current_user": user,
        "invoices": build_invoice_data(db, invoices),
        "success": "开票信息已更新"
    })

@router.post("/{invoice_id}/complete")
async def complete_invoice(request: Request, invoice_id: int, user: dict = Depends(require_login)):
    form_data = await request.form()
    db = request.state.db
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": [], "error": "开票记录不存在"
        })
    if invoice.status != "开票等待中":
        invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": build_invoice_data(db, invoices), "error": "仅开票等待中的记录可标记完成"
        })

    invoice.invoice_number = form_data.get("invoice_number", "").strip() or None
    invoice.status = "开票已完成"
    invoice.completed_at = datetime.now()
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "complete_invoice", f"开票 #{invoice_id}",
                  f"开票完成: {invoice.title}, {invoice.amount}元", client_host)

    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return templates.TemplateResponse("invoices/list.html", {
        "request": request, "current_user": user,
        "invoices": build_invoice_data(db, invoices),
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
        invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
        return templates.TemplateResponse("invoices/list.html", {
            "request": request, "current_user": user, "invoices": build_invoice_data(db, invoices), "error": "仅开票等待中的记录可取消"
        })

    invoice.status = "申请已取消"
    db.commit()

    client_host = request.client.host if request.client else "unknown"
    log_operation(db, user["user_id"], "cancel_invoice", f"开票 #{invoice_id}",
                  f"取消开票申请: {invoice.title}", client_host)

    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return templates.TemplateResponse("invoices/list.html", {
        "request": request, "current_user": user,
        "invoices": build_invoice_data(db, invoices),
        "success": "开票申请已取消"
    })
