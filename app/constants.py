from enum import Enum

class InvoiceStatus(str, Enum):
    PENDING = "开票等待中"
    COMPLETED = "开票已完成"
    CANCELLED = "申请已取消"
    REVERSED = "已冲销"
