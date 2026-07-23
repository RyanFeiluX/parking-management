from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey, Boolean, Numeric, desc
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date

from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="operator")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

class Resident(Base):
    __tablename__ = "residents"
    id = Column(Integer, primary_key=True)
    room_number = Column(String(50), unique=True, nullable=False)
    owner_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    vehicles = relationship("Vehicle", back_populates="resident", order_by="Vehicle.sort_order")

class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True)
    plate_number = Column(String(20), unique=True, nullable=False)
    brand = Column(String(50))
    color = Column(String(20))
    vehicle_type = Column(String(20), default="小车")
    sort_order = Column(Integer, nullable=False, default=1)
    status = Column(String(10), default="正常")
    resident_id = Column(Integer, ForeignKey("residents.id"), nullable=True)
    # 车库属性
    is_garage = Column(Boolean, default=False)  # 是否车库车
    garage_number = Column(String(50), nullable=True)  # 车库编号（唯一）
    garage_valid_until = Column(Date, nullable=True)  # 车库有效期
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    resident = relationship("Resident", back_populates="vehicles")
    payments = relationship("PaymentRecord", back_populates="vehicle", order_by=desc("period_start"))

class FeeTier(Base):
    __tablename__ = "fee_tiers"
    id = Column(Integer, primary_key=True)
    seq_from = Column(Integer, nullable=False)
    seq_to = Column(Integer, nullable=False)
    monthly_fee = Column(Numeric(10, 2), nullable=False)
    quarterly_fee = Column(Numeric(10, 2), nullable=True)
    yearly_fee = Column(Numeric(10, 2), nullable=True)
    effective_date = Column(Date, nullable=False)
    expired_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class DiscountPolicy(Base):
    __tablename__ = "discount_policies"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)
    scope_type = Column(String(20))
    scope_value = Column(String(100))
    apply_seq_from = Column(Integer, default=1)
    apply_seq_to = Column(Integer, default=999)
    effective_date = Column(Date, nullable=False)
    expired_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class PaymentRecord(Base):
    __tablename__ = "payment_records"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    period_type = Column(String(4), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    rule_summary = Column(String(255))
    payment_method = Column(String(20))
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    remark = Column(Text)
    paid_on = Column(Date, default=date.today)
    receipt_date = Column(Date, nullable=False, default=date.today)
    receipt_number = Column(String(50), nullable=False, default="")
    vehicle = relationship("Vehicle", back_populates="payments")
    operator = relationship("User")
    invoice = relationship("Invoice", back_populates="payments")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    tax_id = Column(String(100))
    summary = Column(Text)
    phone = Column(String(20))
    email = Column(String(100))
    bank_name = Column(String(200))
    bank_account = Column(String(100))
    address = Column(String(300))
    invoice_type = Column(String(10), nullable=False, default="普票")
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), nullable=False, default="开票等待中")
    invoice_number = Column(String(100))
    red_invoice_number = Column(String(100))
    cancelled_reason = Column(Text)
    cancelled_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    payments = relationship("PaymentRecord", back_populates="invoice")

class OperationLog(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action_type = Column(String(50), nullable=False)
    target = Column(String(200))
    detail = Column(Text)
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User")

class VehiclePause(Base):
    __tablename__ = "vehicle_pauses"
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False, index=True)
    payment_id = Column(Integer, ForeignKey("payment_records.id"), nullable=True)
    pause_start = Column(Date, nullable=False)
    pause_end = Column(Date, nullable=False)
    pause_months = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    vehicle = relationship("Vehicle")
    payment = relationship("PaymentRecord")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(String(500), nullable=False)
    description = Column(String(200))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)