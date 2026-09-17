"""Medicines router — CRUD + in-date stock count + search/paginate/sort."""

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/medicines", tags=["Medicines"])


def _in_date_stock(medicine_id: int, db: Session) -> int:
    today = date.today()
    result = (
        db.query(func.sum(models.Batch.quantity_remaining))
        .filter(
            models.Batch.medicine_id == medicine_id,
            models.Batch.expiry_date >= today,
            models.Batch.status != models.BatchStatus.quarantined,
        )
        .scalar()
    )
    return result or 0


@router.get("", response_model=schemas.Page)
def list_medicines(
    search: Optional[str] = Query(None, description="Search by name"),
    sort_by: str = Query("name", description="Field to sort by: name | created_at"),
    order: str = Query("asc", description="asc or desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.Medicine)
    if search:
        q = q.filter(models.Medicine.name.ilike(f"%{search}%"))

    sort_col = models.Medicine.name if sort_by == "name" else models.Medicine.created_at
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    out = []
    for m in items:
        d = schemas.MedicineWithStock.model_validate(m)
        d.in_date_stock = _in_date_stock(m.id, db)
        out.append(d)

    return {"total": total, "page": page, "page_size": page_size, "items": out}


@router.post("", response_model=schemas.MedicineOut, status_code=201)
def create_medicine(
    payload: schemas.MedicineCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    if db.query(models.Medicine).filter(models.Medicine.name.ilike(payload.name)).first():
        raise HTTPException(status_code=400, detail="Medicine with this name already exists")
    med = models.Medicine(**payload.model_dump())
    db.add(med)
    db.commit()
    db.refresh(med)
    return med


@router.get("/{medicine_id}", response_model=schemas.MedicineWithStock)
def get_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    med = db.get(models.Medicine, medicine_id)
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    out = schemas.MedicineWithStock.model_validate(med)
    out.in_date_stock = _in_date_stock(medicine_id, db)
    return out


@router.put("/{medicine_id}", response_model=schemas.MedicineOut)
def update_medicine(
    medicine_id: int,
    payload: schemas.MedicineUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    med = db.get(models.Medicine, medicine_id)
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(med, field, value)
    db.commit()
    db.refresh(med)
    return med


@router.delete("/{medicine_id}", status_code=204)
def delete_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    med = db.get(models.Medicine, medicine_id)
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    db.delete(med)
    db.commit()


@router.get("/{medicine_id}/stock")
def get_stock(
    medicine_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    med = db.get(models.Medicine, medicine_id)
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    stock = _in_date_stock(medicine_id, db)
    return {
        "medicine_id": medicine_id,
        "medicine_name": med.name,
        "in_date_stock": stock,
        "unit": med.unit,
        "reorder_threshold": med.reorder_threshold,
        "below_threshold": stock < med.reorder_threshold,
    }
