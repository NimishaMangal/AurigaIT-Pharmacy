"""Pydantic schemas for request validation and response serialisation."""

from datetime import date, datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr, field_validator
from models import BatchStatus


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Medicine ────────────────────────────────────────────────────────────────

class MedicineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    unit: str = "units"
    reorder_threshold: int = 50


class MedicineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    reorder_threshold: Optional[int] = None


class MedicineOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    unit: str
    reorder_threshold: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MedicineWithStock(MedicineOut):
    in_date_stock: int


# ─── Batch ───────────────────────────────────────────────────────────────────

class BatchCreate(BaseModel):
    medicine_id: int
    batch_number: str
    quantity_remaining: int
    expiry_date: date


class BatchOut(BaseModel):
    id: int
    medicine_id: int
    batch_number: str
    quantity_remaining: int
    expiry_date: date
    status: BatchStatus
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Dispense ────────────────────────────────────────────────────────────────

class DispenseRequest(BaseModel):
    medicine_id: int
    quantity: int


class DispenseResult(BaseModel):
    medicine_id: int
    medicine_name: str
    dispensed: int
    batches_used: List[dict]
    remaining_stock: int
    reorder_alert: bool = False


# ─── Clock (L1) ──────────────────────────────────────────────────────────────

class ClockResponse(BaseModel):
    flagged_expiring: int
    quarantined: int
    timestamp: datetime


# ─── Import (L2) ─────────────────────────────────────────────────────────────

class ImportReport(BaseModel):
    imported: int
    deduped: int
    rejected: int
    errors: List[str] = []


# ─── Outbox (L3) ─────────────────────────────────────────────────────────────

class OutboxItem(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    message: str
    current_stock: int
    threshold: int
    delivered: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Pagination wrapper ──────────────────────────────────────────────────────

class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[Any]
