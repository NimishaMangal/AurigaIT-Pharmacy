"""Outbox router — GET /outbox returns the reorder alert queue (L3)."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
import models, schemas

router = APIRouter(tags=["Outbox"])


@router.get("/outbox", response_model=schemas.Page)
def get_outbox(
    delivered: Optional[bool] = Query(None, description="Filter by delivered status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    Returns the reorder-alert outbox. Each item represents a notification
    that was triggered when in-date stock fell below a medicine's threshold.
    """
    q = db.query(models.Outbox)
    if delivered is not None:
        q = q.filter(models.Outbox.delivered == delivered)
    q = q.order_by(models.Outbox.created_at.desc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [schemas.OutboxItem.model_validate(i) for i in items],
    }


@router.patch("/outbox/{item_id}/delivered", response_model=schemas.OutboxItem)
def mark_delivered(
    item_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """Mark a specific outbox notification as delivered."""
    from fastapi import HTTPException
    item = db.get(models.Outbox, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Outbox item not found")
    item.delivered = True
    db.commit()
    db.refresh(item)
    return item
