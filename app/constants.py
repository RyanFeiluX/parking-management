from enum import Enum

class InvoiceStatus(str, Enum):
    PENDING = "开票等待中"
    COMPLETED = "开票已完成"
    CANCELLED = "申请已取消"
    REVERSED = "发票已冲销"

INVOICE_STATUS_LABELS = {
    InvoiceStatus.PENDING: "等待中",
    InvoiceStatus.COMPLETED: "已完成",
    InvoiceStatus.CANCELLED: "申请已取消",
    InvoiceStatus.REVERSED: "已冲销",
}

INVOICE_STATUS_BADGES = {
    InvoiceStatus.PENDING: "badge bg-warning",
    InvoiceStatus.COMPLETED: "badge bg-success",
    InvoiceStatus.CANCELLED: "badge bg-secondary",
    InvoiceStatus.REVERSED: "badge bg-danger",
}

INVOICE_STATUS_ROW_CLASS = {
    InvoiceStatus.CANCELLED: "text-muted",
}

INVOICE_STATUS_CHOICES = [
    (InvoiceStatus.PENDING.value, INVOICE_STATUS_LABELS[InvoiceStatus.PENDING]),
    (InvoiceStatus.COMPLETED.value, INVOICE_STATUS_LABELS[InvoiceStatus.COMPLETED]),
    (InvoiceStatus.CANCELLED.value, INVOICE_STATUS_LABELS[InvoiceStatus.CANCELLED]),
    (InvoiceStatus.REVERSED.value, INVOICE_STATUS_LABELS[InvoiceStatus.REVERSED]),
]
