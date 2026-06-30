from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, List

class UserBase(BaseModel):
    username: str
    display_name: str
    role: str = "operator"
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserResponse(UserBase):
    id: int
    last_login: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True

class ResidentBase(BaseModel):
    room_number: str
    owner_name: str
    phone: Optional[str] = None
    remark: Optional[str] = None

class ResidentCreate(ResidentBase):
    pass

class ResidentUpdate(BaseModel):
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None

class ResidentResponse(ResidentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class VehicleBase(BaseModel):
    plate_number: str
    brand: Optional[str] = None
    color: Optional[str] = None
    vehicle_type: str = "小车"
    sort_order: int = 1
    status: str = "正常"
    resident_id: Optional[int] = None

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    brand: Optional[str] = None
    color: Optional[str] = None
    vehicle_type: Optional[str] = None
    status: Optional[str] = None

class VehicleResponse(VehicleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class FeeTierBase(BaseModel):
    seq_from: int
    seq_to: int
    monthly_fee: float
    quarterly_fee: Optional[float] = None
    yearly_fee: Optional[float] = None
    effective_date: date

class FeeTierCreate(FeeTierBase):
    pass

class FeeTierResponse(FeeTierBase):
    id: int
    expired_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True

class DiscountPolicyBase(BaseModel):
    name: str
    discount_type: str
    discount_value: float
    scope_type: Optional[str] = None
    scope_value: Optional[str] = None
    apply_seq_from: int = 1
    apply_seq_to: int = 999
    effective_date: date

class DiscountPolicyCreate(DiscountPolicyBase):
    pass

class DiscountPolicyResponse(DiscountPolicyBase):
    id: int
    expired_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True

class PaymentRecordBase(BaseModel):
    vehicle_id: int
    period_start: date
    period_end: date
    period_type: str
    amount: float
    rule_summary: Optional[str] = None
    payment_method: Optional[str] = None
    remark: Optional[str] = None

class PaymentRecordCreate(PaymentRecordBase):
    operator_id: Optional[int] = None

class PaymentRecordResponse(PaymentRecordBase):
    id: int
    paid_at: datetime

    class Config:
        orm_mode = True

class SystemSettingBase(BaseModel):
    key: str
    value: str
    description: Optional[str] = None

class SystemSettingCreate(SystemSettingBase):
    pass

class SystemSettingResponse(SystemSettingBase):
    id: int
    updated_at: datetime

    class Config:
        orm_mode = True

class InvoiceCreate(BaseModel):
    payment_ids: List[int]
    title: str
    tax_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    summary: Optional[str] = None
    invoice_type: str = "普票"
    amount: float

class InvoiceUpdate(BaseModel):
    title: Optional[str] = None
    tax_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    summary: Optional[str] = None
    invoice_type: Optional[str] = None
    amount: Optional[float] = None

class InvoiceResponse(BaseModel):
    id: int
    title: str
    tax_id: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    summary: Optional[str] = None
    invoice_type: str
    amount: float
    status: str
    invoice_number: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

class LoginForm(BaseModel):
    username: str
    password: str

class SetupForm(BaseModel):
    username: str
    display_name: str
    password: str
    confirm_password: str

class ChangePasswordForm(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str