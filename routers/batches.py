"""Batches router — add, list, get, delete batches."""

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(prefix="/batches", tags=["Batches"])


@router.get("", response_model=schemas.Page)
def list_batches(
    medicine_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None, description="Search by batch_number"),
    status: Optional[str] = Query(None, description="Filter by status: active|expiring_soon|quarantined"),
    sort_by: str = Query("expiry_date", description="expiry_date | created_at | quantity_remaining"),
    order: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    q = db.query(models.Batch)
    if medicine_id:
        q = q.filter(models.Batch.medicine_id == medicine_id)
    if search:
        q = q.filter(models.Batch.batch_number.ilike(f"%{search}%"))
    if status:
        q = q.filter(models.Batch.status == status)

    col_map = {
        "expiry_date": models.Batch.expiry_date,
        "created_at": models.Batch.created_at,
        "quantity_remaining": models.Batch.quantity_remaining,
    }
    sort_col = col_map.get(sort_by, models.Batch.expiry_date)
    q = q.order_by(sort_col.desc() if order == "desc" else sort_col.asc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [schemas.BatchOut.model_validate(b) for b in items]}


@router.post("", response_model=schemas.BatchOut, status_code=201)
def add_batch(
    payload: schemas.BatchCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    if not db.get(models.Medicine, payload.medicine_id):
        raise HTTPException(status_code=404, detail="Medicine not found")

    status = models.BatchStatus.active
    if payload.expiry_date < date.today():
        status = models.BatchStatus.quarantined

    batch = models.Batch(**payload.model_dump(), status=status)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/{batch_id}", response_model=schemas.BatchOut)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    batch = db.get(models.Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.delete("/{batch_id}", status_code=204)
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    batch = db.get(models.Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    db.delete(batch)
    db.commit()
