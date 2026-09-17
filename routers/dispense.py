"""Dispense router — POST /dispense (FIFO)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from services.fifo import dispense_medicine
import models, schemas

router = APIRouter(tags=["Dispense"])


@router.post("/dispense", response_model=schemas.DispenseResult)
def dispense(
    payload: schemas.DispenseRequest,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """
    Dispense `quantity` units of a medicine using FIFO (First-Expiry-First-Out).
    Expired and quarantined batches are never used. Triggers a reorder alert
    if remaining in-date stock drops below the medicine's threshold.
    """
    return dispense_medicine(payload.medicine_id, payload.quantity, db)
